"""Refine Executor for HTML Generation"""

import re
import json
import argparse
import warnings
from pathlib import Path
from itertools import combinations

import numpy as np
import statsmodels.api as sm
from scipy.stats import ttest_rel
from sklearn.metrics import adjusted_rand_score
from statsmodels.stats.multitest import multipletests


from common.config import RESOLUTION_LIST, get_html_name_list
from common.score import load_comparison_from_json
from metrics.utils.typings import ComparisonResults
from multi_agent.utils.typings import InitialType, FeedbackType
from scripts.evaluate import SCORE_HEADERS

APPROACH_DICT = {
    InitialType.SINGLE.value: "SingleRef",
    InitialType.MULTI.value: "MultiRef",
    f"{InitialType.MULTI.value}_{FeedbackType.SPECIFIC.value}": "AgentSpec",
    f"{InitialType.MULTI.value}_{FeedbackType.GENERAL.value}": "AgentGen",
    f"{InitialType.MULTI.value}_{FeedbackType.GENERAL.value}_focus": "AgentGen+",
}


def _read_scores_from_csv(score_file_path: Path) -> np.ndarray:
    """Read the score CSV file and return a numpy array of scores.

    The CSV file is expected to have the following format:
    file_name,score1,score2,score3,...
    """
    if not score_file_path.exists():
        raise FileNotFoundError(f"Score file {score_file_path} does not exist.")

    with open(score_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        score_matrix = []
        for line in lines[1:]:  # Skip header line
            parts = line.strip().split(",")
            scores = list(map(float, parts[1:]))  # Convert score strings to floats
            score_matrix.append(scores)
        return np.array(score_matrix)  # Shape: (file, metric_score)


def _write_scores_to_latex_table(
    latex_output_file_path: Path,
    approach_labels: list[str],
    score_matrix: np.ndarray,  # 4D matrix: (file, metric_score, approach, resolution)
):
    """Write the aggregated scores to a LaTeX table for report generation."""

    # Average across files: (metric_score, approach, resolution)
    file_score_matrix = np.mean(score_matrix, axis=0)
    # Standard deviation across resolutions: (metric_score, approach)
    mean_std_matrix = np.std(score_matrix, axis=3).mean(axis=0)

    for score_index, score_name in enumerate(SCORE_HEADERS[1:]):
        score_file = latex_output_file_path.with_stem(f"{latex_output_file_path.stem}_{score_name}")
        score_file.parent.mkdir(parents=True, exist_ok=True)
        with open(score_file, "w", encoding="utf-8") as f:
            f.write("\\begin{tabularx}{\\columnwidth}{>{\\hsize=1.8\\hsize}X *{8}{>{\\hsize=0.9\\hsize}X}}\n")
            f.write("\\toprule\n")
            f.write("Approaches & Mean & ResSD & " + " & ".join([f"{res[0]}x" for res in RESOLUTION_LIST]))
            f.write(" \\\\\n")
            f.write("\\midrule\n")
            for approach_idx, approach in enumerate(approach_labels):
                # Average across resolutions
                mean_score_list = file_score_matrix[score_index, approach_idx, :]
                mean_score = 100 * np.mean(mean_score_list)
                mean_res_std = 100 * mean_std_matrix[score_index, approach_idx]
                row_score_list = [f"{100*mean:.2f}" for mean in mean_score_list]
                f.write(f"{approach} & {mean_score:.2f} & {mean_res_std:.2f} & {' & '.join(row_score_list)} \\\\\n")
            f.write("\\bottomrule\n")
            f.write("\\end{tabularx}\n")


def _write_paired_test_to_latex_table(
    latex_output_file_path: Path,
    approach_labels: list[str],
    score_matrix: np.ndarray,  # 2D matrix: (file, approach)
    diff_label: str = "score",
):
    # Calculate the mean score for each approach across files
    approach_mean_scores = score_matrix.mean(axis=0)

    # Define the pairs of approaches to compare for the paired t-test
    ttest_idx_pair = list(combinations(range(len(approach_labels)), 2))

    latex_output_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(latex_output_file_path, "w", encoding="utf-8") as f:
        f.write(r"\begin{tabularx}{\columnwidth}{l *{5}{>{\centering\arraybackslash}X}}")
        f.write("\n\\toprule\n")
        f.write(f"Comparison & $\\Delta${diff_label} & $t$ & $p$ & $p_{{\\text{{adj}}}}$ & Sig. \\\\\n")
        f.write("\\midrule\n")

        result = []
        for idx_pair in ttest_idx_pair:
            idx1, idx2 = idx_pair
            label = f"{approach_labels[idx1]} vs {approach_labels[idx2]}"
            score_diff = 100 * (approach_mean_scores[idx1] - approach_mean_scores[idx2])
            t_value, p_value = ttest_rel(score_matrix[:, idx1], score_matrix[:, idx2])
            result.append((label, score_diff, t_value, p_value))

        # Apply multiple testing correction
        reject, corrected_p_values, _, _ = multipletests([r[-1] for r in result], alpha=0.05, method="holm")
        for i, (label, score_diff, t_value, p_value) in enumerate(result):
            p_adj = f"{corrected_p_values[i]:.3f}"
            p_sig = "*" if reject[i] else "n.s."
            f.write(f"{label} & {score_diff:.1f} & {t_value:.3f} & {p_value:.3f} & {p_adj} & {p_sig} \\\\\n")

        f.write("\\bottomrule\n")
        f.write("\\end{tabularx}\n")


def _write_logitics_to_latex_table(
    latex_output_file_path: Path,
    approach_labels: list[str],
    predicted_model: list[sm.Logit],
):
    """Write the logistic regression results to a LaTeX table for report generation."""

    def _format_logitics(model: sm.Logit) -> tuple[str, str]:
        intercept = model.params[0]
        coef = model.params[1]
        threshold = -intercept / coef if coef != 0 else float("inf")
        pseudo_r2 = model.prsquared
        p_value_score = "$<0.001$" if model.pvalues[1] < 0.001 else f"{model.pvalues[1]:.3f}"
        return (intercept, coef, threshold, pseudo_r2, p_value_score)

    latex_output_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(latex_output_file_path, "w", encoding="utf-8") as f:
        f.write(r"\begin{tabularx}{\columnwidth}{X *{5}{>{\centering\arraybackslash}X}}")
        f.write("\n\\toprule\n")
        f.write("Feedback & Intercept  & Coef. & Threshold & Pseudo$R^2$ & P-value \\\\\n")
        f.write("\\midrule\n")
        for approach_label, model in zip(approach_labels, predicted_model):
            intercept, coef, threshold, pseudo_r2, p_value_score = _format_logitics(model)
            f.write(
                f"{approach_label} & {intercept:.3f} & {coef:.3f} & {threshold:.3f} & {pseudo_r2:.3f} & {p_value_score} \\\\\n"
            )
        f.write("\\bottomrule\n")
        f.write("\\end{tabularx}\n")


def _collect_cluster_differences(comparison: ComparisonResults) -> tuple[list[str], list[tuple[str, str]]]:
    """Extract unmatched nodes and matched pairs from a comparison result.

    Output IDs are namespaced:
      - source node ID: "s_<id>"
      - generated node ID: "g_<id>"
    """
    matched_node_ids = comparison.node_ids or []
    source_nodes = comparison.source_elements.nodes or {}
    generated_nodes = comparison.generated_elements.nodes or {}

    all_source_ids = set(source_nodes.keys())
    all_generated_ids = set(generated_nodes.keys())
    matched_source_ids = {sid for sid, _ in matched_node_ids}
    matched_generated_ids = {gid for _, gid in matched_node_ids}

    # Combine unmatched nodes from both source and generated for unified handling
    unmatched_source_nodes = [f"s_{sid}" for sid in sorted(all_source_ids - matched_source_ids)]
    unmatched_generated_nodes = [f"g_{gid}" for gid in sorted(all_generated_ids - matched_generated_ids)]
    unmatched_nodes = unmatched_source_nodes + unmatched_generated_nodes

    # Create matched pairs with namespaced IDs
    matched_pairs = [(f"s_{sid}", f"g_{gid}") for sid, gid in matched_node_ids]

    return unmatched_nodes, matched_pairs


def _calculate_rand_score(
    true_singletons: list[str],
    pred_singletons: list[str],
    true_pairs: list[tuple[str, str]],
    pred_pairs: list[tuple[str, str]],
) -> float:
    """Calculate the Adjusted Rand Score between two clusterings represented as pairs and singletons."""

    # Step 1: unified node set (include singletons explicitly)
    nodes = sorted({n for pair in (true_pairs + pred_pairs) for n in pair}.union(true_singletons, pred_singletons))

    def build_labels(pairs, singletons):
        parent = {n: n for n in nodes}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Step 2: build clusters from pairs
        for a, b in pairs:
            union(a, b)

        # Step 3: ensure singleton nodes stay singleton
        for n in singletons:
            parent.setdefault(n, n)

        # Step 4: assign cluster IDs
        root_to_id = {}
        labels = []
        next_id = 0

        for n in nodes:
            r = find(n)
            if r not in root_to_id:
                root_to_id[r] = next_id
                next_id += 1
            labels.append(root_to_id[r])

        return labels

    labels_true = build_labels(true_pairs, true_singletons)
    labels_pred = build_labels(pred_pairs, pred_singletons)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"The number of unique classes is greater than 50% *",
            category=UserWarning,
        )
        return adjusted_rand_score(labels_true, labels_pred)


def create_auto_score_report(model_name: str, max_version: int = 1):
    """Generate evaluation reports based on the collected scores."""

    # Generate resolution labels for the report analysis
    resolutions = [f"{s[0]}x{s[1]}" for s in RESOLUTION_LIST]

    approach_matrix = []  # 5D matrix: (approach, version, resolution, file, metric_score)
    approach_labels = list(APPROACH_DICT.values())
    for approach in APPROACH_DICT:
        version_matrix = []  # 4D matrix: (version, resolution, file, metric_score)
        for version in range(max_version):
            resolution_matrix = []  # 3D matrix: (resolution, file, metric_score)
            for resolution in resolutions:
                score_file_name = f"{model_name}_0{version+1}_{approach}.csv"
                score_file_path = Path(f"results/scores/{resolution}/{score_file_name}")

                if not score_file_path.exists():
                    print(f"Warning: Score file {score_file_path} does not exist. Skipping.")
                    resolution_matrix = []  # Reset score matrix if any file is missing
                    continue

                file_metric_scores = _read_scores_from_csv(score_file_path)
                resolution_matrix.append(file_metric_scores)
            version_matrix.append(resolution_matrix)

        # Check if we have collected scores for all versions before calculating mean and std
        if version_matrix:
            approach_matrix.append(version_matrix)

    # Print the shape of the collected score matrix for debugging
    matrix_shape = np.array(approach_matrix).shape
    matrix_labels = ["approach", "version", "resolution", "file", "score"]
    print("Auto Score Report Dimensions:", dict(zip(matrix_labels, matrix_shape)))

    # Calculate the mean across versions, resulting in a 4D matrix: (approach, resolution, file, metric_score)
    mean_approach_matrix = np.mean(approach_matrix, axis=1)  # Average across versions

    # Convert the approach matrix to a numpy array and transpose (file, metric_score, approach, resolution)
    all_matched_matrix = mean_approach_matrix.transpose([2, 3, 0, 1])

    # Write the scores to LaTeX tables for report generation
    _write_scores_to_latex_table(
        latex_output_file_path=Path(f"results/report/auto_score/{model_name}.tex"),
        approach_labels=approach_labels,
        score_matrix=all_matched_matrix,
    )
    # For paired t-tests, we focus on the total score (the first score) and average across resolutions for each file
    paired_test_score_matrix = np.array(all_matched_matrix)[:, 0, :, :]  # 3D matrix: (file, approach, resolution)
    _write_paired_test_to_latex_table(
        latex_output_file_path=Path(f"results/report/auto_score/{model_name}_score.tex"),
        approach_labels=approach_labels,
        diff_label="Mean",
        score_matrix=paired_test_score_matrix.mean(
            axis=2
        ),  # Mean scores across resolutions for each file: (file, approach)
    )
    _write_paired_test_to_latex_table(
        latex_output_file_path=Path(f"results/report/auto_score/{model_name}_sd.tex"),
        approach_labels=approach_labels,
        diff_label="ResSD",
        score_matrix=paired_test_score_matrix.std(
            axis=2
        ),  # Standard deviation across resolutions for each file: (file, approach)
    )


def create_feedback_report(model_name: str, max_version: int = 1):
    """Generate a report comparing the feedback types for the multi-agent approach."""

    def _get_feedback_data(feedback_type: FeedbackType, version: int, html_name: str) -> dict:
        approach = f"{InitialType.MULTI.value}_{feedback_type.value}"
        folder_str = f"results/{model_name}_0{version+1}/{approach}/iter_00/feedbacks/"
        feedback_file = Path(folder_str) / f"{Path(html_name).stem}.json"
        if not feedback_file.exists():
            print(f"Warning: Feedback file {feedback_file} does not exist. Skipping.")
            return {}
        with open(feedback_file, "r", encoding="utf-8") as f:
            return json.load(f)

    results = []
    html_name_list = get_html_name_list()
    score_path = Path("results/scores/res-mean")
    for version in range(max_version):
        multi_score_stem = f"{model_name}_0{version+1}_{InitialType.MULTI.value}"
        multi_scores = _read_scores_from_csv(score_path / f"{multi_score_stem}.csv")

        for idx, html_name in enumerate(html_name_list):
            html_stem = Path(html_name).stem
            general_feedback_data = _get_feedback_data(FeedbackType.GENERAL, version, html_name)
            specific_feedback_data = _get_feedback_data(FeedbackType.SPECIFIC, version, html_name)

            has_general_feedback = 1 if general_feedback_data else 0
            has_specific_feedback = 1 if specific_feedback_data else 0
            results.append((version, html_stem, has_general_feedback, has_specific_feedback, multi_scores[idx][0]))

    output_path = Path(f"results/report/plot_data/{model_name}_feedback.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("version,name,has_general_feedback,has_specific_feedback,score\n")
        for result in results:
            f.write(",".join(map(str, result)) + "\n")
    print(f"Feedback report saved to: {output_path}")

    _, _, general_flags, specific_flags, scores = zip(*results)
    score_sm = sm.add_constant(scores)
    gen_model = sm.Logit(general_flags, score_sm).fit(disp=0)
    spec_model = sm.Logit(specific_flags, score_sm).fit(disp=0)
    output_path = Path(f"results/report/manual/{model_name}_feedback_logitics.tex")
    _write_logitics_to_latex_table(
        latex_output_file_path=output_path,
        approach_labels=["General", "Specific"],
        predicted_model=[gen_model, spec_model],
    )
    print(f"Logistic regression report saved to: {output_path}")


def create_revision_report(model_name: str, max_version: int = 1):
    """Generate a report comparing the revision content for the multi-agent approach."""

    results = []
    html_name_list = get_html_name_list()
    score_path = Path("results/scores/res-mean")
    for version in range(max_version):
        approach_stem = f"{model_name}_0{version+1}_{InitialType.MULTI.value}"
        multi_scores = _read_scores_from_csv(score_path / f"{approach_stem}.csv")
        approach_stem += f"_{FeedbackType.GENERAL.value}"
        revise_scores = _read_scores_from_csv(score_path / f"{approach_stem}.csv")
        focus_revise_scores = _read_scores_from_csv(score_path / f"{approach_stem}_focus.csv")
        for idx, html_name in enumerate(html_name_list):
            html_stem = Path(html_name).stem
            base_score = multi_scores[idx][0] * 100
            revision_diff = (
                revise_scores[idx][0] * 100 - base_score,
                focus_revise_scores[idx][0] * 100 - base_score,
            )
            results.append((version, html_stem, base_score) + revision_diff)

    output_path = Path(f"results/report/plot_data/{model_name}_revision.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("version,name,base_score,revise_diff,focus_revise_diff\n")
        for result in results:
            f.write(",".join(map(str, result)) + "\n")
    print(f"Revision report saved to: {output_path}")


def calculate_clustering_similarity(model_name: str, max_version: int = 1):
    """Calculate the clustering similarity (e.g., Adjusted Rand Score) between auto and manual matching."""

    is_exception = False
    sample_name_list = get_html_name_list(dataset="samples")
    approach_matrix = []  # 4D matrix: (approach, version, file, resolution)
    for approach in APPROACH_DICT:
        version_matrix = []  # 3D matrix: (version, file, resolution)
        for version in range(max_version):
            file_matrix = []  # 2D matrix: (file, resolution)
            for sample_name in sample_name_list:
                folder_str = f"results/{model_name}_0{version+1}/{approach}/iter_01/"
                sample_stem = Path(sample_name).stem
                sample_html_path = Path(folder_str) / sample_name

                if not sample_html_path.exists():
                    sample_html_path = Path(re.sub(r"multi_\w+", "multi", folder_str)) / sample_name

                auto_score_path = sample_html_path.parent / "auto_score" / f"{sample_stem}.json"
                manual_score_path = sample_html_path.parent / "manual_score" / f"{sample_stem}.json"

                if not auto_score_path.exists():
                    print(f"Warning: Auto score file {auto_score_path} does not exist. Skipping.")
                    is_exception = True
                    continue
                if not manual_score_path.exists():
                    print(f"Warning: Manual score file {manual_score_path} does not exist. Skipping.")
                    is_exception = True
                    continue

                rand_scores = []
                auto_score_data = load_comparison_from_json(auto_score_path)
                manual_score_data = load_comparison_from_json(manual_score_path)
                for resolution in auto_score_data:
                    auto_unmatched, auto_matched = _collect_cluster_differences(auto_score_data[resolution])
                    manual_unmatched, manual_matched = _collect_cluster_differences(manual_score_data[resolution])
                    rand_score = _calculate_rand_score(
                        true_singletons=manual_unmatched,
                        pred_singletons=auto_unmatched,
                        true_pairs=manual_matched,
                        pred_pairs=auto_matched,
                    )
                    rand_scores.append(rand_score)
                file_matrix.append(rand_scores)
            version_matrix.append(file_matrix)
        approach_matrix.append(version_matrix)

    if is_exception:
        print("Some score files are missing. Please check the warnings above and ensure all score files are available.")
        return

    # Print the shape of the collected score matrix for debugging
    matrix_labels = ["approach", "version", "file", "resolution"]
    print("Clustering Similarity Report Dimensions:", dict(zip(matrix_labels, np.array(approach_matrix).shape)))

    # Calculate the overall mean Rand score across approaches, versions, files, and resolutions
    print(f"Overall Mean Adjusted Rand Score: {np.mean(approach_matrix):.4f}")

    # Average across approaches, versions, and resolutions
    file_mean_rand_scores = np.mean(approach_matrix, axis=(0, 1, 3))
    Path("results/report/plot_data").mkdir(parents=True, exist_ok=True)
    with open(f"results/report/plot_data/{model_name}_rand_scores.csv", "w", encoding="utf-8") as f:
        f.write("file,mean_adjusted_rand_score\n")
        for idx, sample_name in enumerate(sample_name_list):
            f.write(f"{sample_name},{file_mean_rand_scores[idx]:.4f}\n")


if __name__ == "__main__":
    HELP_INFO = """
Generate evaluation reports for generated HTML files.
Usage:
  python -m scripts.report --model MODEL_NAME [--version VERSION] 
Example:
  python -m scripts.report
"""
    # Initialize the parser
    parser = argparse.ArgumentParser(description=HELP_INFO)

    # Define the arguments
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.1-codex-mini",
        help="Model to use for generation (default: gpt-5.1-codex-mini)",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="Max version of the generated HTML to include in the report (default: 1)",
    )

    # Parse the arguments
    args = parser.parse_args()
    arg_model_name = re.sub(r"\w+/", "", args.model)
    create_auto_score_report(arg_model_name, max_version=args.version)
    create_feedback_report(arg_model_name, max_version=args.version)
    create_revision_report(arg_model_name, max_version=args.version)
    calculate_clustering_similarity(arg_model_name, max_version=args.version)
