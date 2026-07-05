"""Refine Executor for HTML Generation"""

import re
import json
import shutil
import argparse
import asyncio
from pathlib import Path

import numpy as np
from tqdm import tqdm

from common.config import get_html_name_list, get_page_config, RESOLUTION_LIST
from common.logger import common_logger
from common.browser import launch_browser
from common.json_output import json_serializable
from common.score import evaluate_metadata, generate_report_scores, load_comparison_from_json
from common.metadata import generate_metadata, load_metadata_from_json

from multi_agent.utils.typings import InitialType, FeedbackType

SCORE_HEADERS = [
    "name",
    "overall_score",
    "module_coverage",
    "module_score",
    "node_coverage",
    "node_score",
]

APPROACHE_KEYS = [
    InitialType.SINGLE.value,
    InitialType.MULTI.value,
    InitialType.MULTI.value + "_" + FeedbackType.SPECIFIC.value,
    InitialType.MULTI.value + "_" + FeedbackType.GENERAL.value,
    InitialType.MULTI.value + "_" + FeedbackType.GENERAL.value + "_focus",
]


def _write_scores_to_csv_file(root_path: str, group_name: str, file_names: list[str], file_score_matrix: np.ndarray):
    """Write the aggregated scores to CSV files for report generation"""

    # Get resolution labels for the report
    resolutions = [f"{s[0]}x{s[1]}" for s in RESOLUTION_LIST]

    # Calculate overall average scores across all files for each resolution and metric -> (resolution, metric_score)
    resolution_metric_avg = np.mean(file_score_matrix, axis=0) if file_score_matrix else np.array([])
    # Calculate overall mean score across all resolutions for each metric -> (metric_score,)
    overall_metric_means = np.mean(resolution_metric_avg, axis=0) if resolution_metric_avg.size > 0 else np.array([])
    resolution_score_table = np.vstack(
        (
            SCORE_HEADERS,
            np.column_stack((resolutions, resolution_metric_avg)),
            ["ResMean", *overall_metric_means],
        )
    )

    # Transpose file_score_matrix to group by resolution -> (resolution, file, metric_score)
    resolution_grouped_scores = np.transpose(file_score_matrix, (1, 0, 2))
    resolution_file_score_tables = {}
    for i, score in enumerate(resolution_grouped_scores):
        resolution = resolutions[i]
        file_scores = np.column_stack((file_names, score))
        resolution_file_score_tables[resolution] = np.vstack((SCORE_HEADERS, file_scores))

    res_mean_scores = resolution_grouped_scores.mean(axis=0)
    file_scores = np.column_stack((file_names, res_mean_scores))
    resolution_file_score_tables["res-mean"] = np.vstack((SCORE_HEADERS, file_scores))

    # Save the scores to CSV files for report generation
    score_file_path = Path(f"{root_path}_{group_name}.csv")
    score_file_name = score_file_path.name
    score_file_folder = score_file_path.parent
    score_file_folder = score_file_folder / "scores"
    score_file_folder.mkdir(parents=True, exist_ok=True)
    with open(score_file_folder / score_file_name, "w", encoding="utf-8") as f:
        for score_data_row in resolution_score_table:
            f.write(",".join(map(str, score_data_row)) + "\n")

    for resolution, file_scores in resolution_file_score_tables.items():
        resolution_scores_folder = score_file_folder / resolution
        resolution_scores_folder.mkdir(parents=True, exist_ok=True)
        with open(resolution_scores_folder / score_file_name, "w", encoding="utf-8") as f:
            for score_data_row in file_scores:
                f.write(",".join(map(str, score_data_row)) + "\n")


async def _evaluate_file_list(
    root_path: str,
    approach: str,
    name_list: list[str],
    iteration: int = 1,
):
    """Evaluate the generated HTML files for a given model, file list, and iteration."""

    # Placeholder for evaluation logic
    file_scores_collection: dict[str, dict] = {}

    async with launch_browser() as browser:
        with tqdm(name_list, dynamic_ncols=True, leave=True) as progress_bar:
            for page_name in progress_bar:
                progress_bar.set_description(page_name)

                eval_config = get_page_config(f"{root_path}/{approach}", page_name, iteration)
                eval_html_path = eval_config.get_html_path()

                auto_score_path = Path(eval_config.metadata.replace("metadata/", "auto_score/"))
                Path(auto_score_path).parent.mkdir(parents=True, exist_ok=True)

                if eval_html_path.exists():
                    # Try to read the HTML content to ensure it's not empty before proceeding with evaluation
                    try:
                        html_content = eval_html_path.read_text(encoding="utf-8")
                        if not html_content.strip():
                            common_logger.warning(
                                "Empty HTML content found for page: %s (%s)", page_name, eval_html_path
                            )
                            continue
                    except OSError as exc:
                        common_logger.warning(
                            "Failed to read HTML for page %s (%s): %s", page_name, eval_html_path, exc
                        )
                        continue

                    # Load base metadata from datasets
                    base_metadata = load_metadata_from_json("datasets/metadata/" + page_name.replace(".html", ".json"))
                    # Load existing metadata for the evaluation HTML file if it is exist, otherwise generate metadata
                    eval_metadata = await generate_metadata(browser=browser, config=eval_config, overwrite=False)
                    comparison_results = evaluate_metadata(base_metadata, eval_metadata)

                    # Save individual file scores to JSON for later analysis
                    with open(auto_score_path, "w", encoding="utf-8") as f:
                        json.dump(comparison_results, f, default=json_serializable, indent=2)
                else:
                    # If the evaluation HTML file does not exist, directly copy the result from the original version
                    base_approach = approach.split("_")[0]  # Extract the base approach (e.g., "single" or "multi")
                    fallback_config = get_page_config(f"{root_path}/{base_approach}", page_name, 1)
                    fallback_score_path = Path(fallback_config.metadata.replace("metadata/", "auto_score/"))
                    comparison_results = load_comparison_from_json(fallback_score_path)

                    # Copy the fallback score to the current approach's auto_score directory for later analysis
                    shutil.copy(fallback_score_path, auto_score_path)
                file_scores_collection[page_name] = comparison_results

    return file_scores_collection


async def _evaluate_and_output_scores(
    root_path: str,
    approach: str,
):
    """Evaluate the generated HTML files for a given model and file."""

    print(f"Evaluating approach: {approach}")

    name_list = get_html_name_list()
    file_scores_collection = await _evaluate_file_list(root_path, approach, name_list, iteration=1)
    file_score_matrix = generate_report_scores(file_scores_collection)
    _write_scores_to_csv_file(root_path, approach, name_list, file_score_matrix)


async def evaluate_iteration(root_path: str, iteration: int, dataset: str):
    """Evaluate the generated HTML files for a given model, file, and iteration."""

    base_approach = APPROACHE_KEYS[1]  # Multi approach is used as the base approach for iteration evaluation
    eval_approach = APPROACHE_KEYS[-1]  # Multi General Focus approach is used as the evaluation approach
    print(f"Evaluating approach: {eval_approach}, iteration: {iteration}")

    name_list = get_html_name_list(dataset=dataset)
    base_score_collection = await _evaluate_file_list(root_path, base_approach, name_list, iteration=iteration)
    score_matrix = generate_report_scores(base_score_collection)
    base_score_list = np.array(score_matrix).mean(axis=1)[:, 0] * 100

    iter_score_map = {}
    for num in range(1, iteration + 1):
        iter_name_list = []
        for page_name in name_list:
            iter_html_path = Path(f"{root_path}/{eval_approach}/iter_{num:02X}/{page_name}")
            if iter_html_path.exists():
                iter_name_list.append(page_name)
        if not iter_name_list:
            break  # If no files exist for this iteration, stop the evaluation loop

        score_collection = await _evaluate_file_list(root_path, eval_approach, iter_name_list, iteration=num)
        score_matrix = generate_report_scores(score_collection)
        iter_score_list = np.array(score_matrix).mean(axis=1)[:, 0]
        for page_name, score in zip(iter_name_list, iter_score_list):
            iter_score_map.setdefault(page_name, {})[num] = score * 100

    output_path = Path(f"results/scores/iteration/{eval_approach}_{iteration:02X}_{dataset}.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("name,base_score")
        for num in range(1, iteration + 1):
            f.write(f",iter_{num:02X}")
        f.write("\n")

        for page_name, score in zip(name_list, base_score_list):
            f.write(f"{page_name},{score}")
            for num in range(1, iteration + 1):
                iter_score = iter_score_map.get(page_name, {}).get(num, "")
                f.write(f",{iter_score}")
            f.write("\n")
    print(f"Iteration evaluation scores saved to: {output_path}")


def evaluate_action_all(root_path: str):
    """Evaluate the generated HTML files for all prompt and feedback types."""
    for approach in APPROACHE_KEYS:
        if not Path(f"{root_path}/{approach}").exists():
            print(f"Warning: Directory for approach '{approach}' does not exist in {root_path}. Skipping.")
            continue  # Skip if the directory for this approach does not exist

        asyncio.run(_evaluate_and_output_scores(root_path, approach))


if __name__ == "__main__":
    HELP_INFO = """
Evaluate the generated HTML files for a specified model and version. 
The result will be saved in a CSV file under the results directory.
Usage:
    python -m scripts.evaluate --model MODEL_NAME [--version VERSION]
Example:
    python -m scripts.evaluate
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
        "--version", type=int, default=1, help="Max version of the generated HTML to evaluate (default: 1)"
    )
    parser.add_argument("--iteration", type=int, help="Max iteration of the generated HTML to evaluate")

    # Parse the arguments
    args = parser.parse_args()
    model_name = re.sub(r"\w+/", "", args.model)
    if args.iteration is None:
        for version in range(1, args.version + 1):
            print(f"Evaluating model: {model_name}, version: {version}")
            evaluate_action_all(f"results/{model_name}_{version:02X}")
    else:
        asyncio.run(
            evaluate_iteration(f"results/{model_name}_{args.version:02X}", iteration=args.iteration, dataset="html")
        )
