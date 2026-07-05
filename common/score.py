"""Module for generating auto score based on metadata."""

import re
import json
from pathlib import Path

from metrics.utils.typings import ComparisonResults, PageElements
from metrics.dom_evaluator import evaluate


def evaluate_metadata(
    base_metadata: dict[str, PageElements], eval_metadata: dict[str, PageElements], disable_merge: bool = False
) -> dict[str, ComparisonResults]:
    """Generate auto score by evaluating the base metadata and eval metadata."""

    result: dict[str, ComparisonResults] = {}
    pre_module_ids: list[tuple[str, str]] = []
    pre_node_ids: list[tuple[str, str]] = []
    for resolution, base_elems in base_metadata.items():
        eval_elems = eval_metadata.get(resolution)
        eval_result = evaluate(base_elems, eval_elems, resolution, pre_module_ids, pre_node_ids, disable_merge)
        result[resolution] = eval_result

        pre_module_ids = eval_result.module_ids
        pre_node_ids = eval_result.node_ids

    return result


def generate_report_scores(file_scores_collection: dict[dict[str, ComparisonResults]]):
    """Aggregate and summarize scores from a collection of file scores for report generation."""

    file_score_matrix = []  # 3D matrix: (file, resolution, metric_score)
    for file_score_data in file_scores_collection.values():
        resolution_scores = []  # 2D matrix: (resolution, metric_score)
        for resolution in file_score_data:
            scores = []
            for key in ["module", "node"]:
                stats = getattr(file_score_data[resolution], f"{key}_stats", {})
                coverage = stats.get("coverage", 0)
                if key == "module":
                    score = (
                        stats.get("text_score", 0) * 0.5
                        + stats.get("shape_score", 0) * 0.25
                        + stats.get("position_score", 0) * 0.25
                    )
                elif key == "node":
                    score = (
                        stats.get("iou_score", 0) * 0.5
                        + stats.get("text_score", 0) * 0.25
                        + stats.get("color_score", 0) * 0.25
                    )
                else:
                    score = 0
                scores += [coverage, score]
            sum_score = scores[0] * scores[1] * 0.5 + scores[2] * scores[3] * 0.5
            resolution_scores.append([sum_score] + scores)
        file_score_matrix.append(resolution_scores)

    return file_score_matrix


def load_comparison_from_json(path: Path) -> dict[str, ComparisonResults]:
    """Read an existing metadata JSON file into ComparisonResults."""
    with open(path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    return {k: ComparisonResults.from_json(v) for k, v in json_data.items() if re.match(r"^\d+x\d+$", k)}
