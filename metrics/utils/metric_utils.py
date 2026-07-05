"""Utility functions for metric calculations"""

import re
import numpy as np

from scipy.optimize import linear_sum_assignment
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer

from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

from common.logger import common_logger
from metrics.utils.typings import BoundingBox

# This is a patch for color map, which is not updated for newer version of numpy
setattr(np, "asscalar", lambda a: a.item())


def calculate_color_similarity(color1: str, color2: str) -> float:
    """Calculate color similarity (0.0-1.0) between two rgb color strings using CIEDE2000."""

    def _parse_color(color_str: str) -> sRGBColor:
        if not color_str.startswith("rgb"):
            raise ValueError(f"Unsupported color format: {color_str}")
        try:
            color_match = re.match(r"rgb\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})\)", color_str)
            r, g, b = map(int, color_match.groups())
            return sRGBColor(r / 255.0, g / 255.0, b / 255.0)
        except (AttributeError, ValueError, TypeError) as exc:
            common_logger.error("Failed to parse color string: %s. Error: %s", color_str, exc)
            raise exc

    try:
        c1_rgb = _parse_color(color1)
        c2_rgb = _parse_color(color2)
        c1_lab = convert_color(c1_rgb, LabColor)
        c2_lab = convert_color(c2_rgb, LabColor)
        delta_e = delta_e_cie2000(c1_lab, c2_lab)
        similarity = max(0.0, 1 - delta_e / 100)  # Normalize to [0,1]
        return similarity
    except (AttributeError, ValueError, TypeError) as exc:
        common_logger.error("Error calculating color similarity for '%s' and '%s': %s", color1, color2, exc)
        return 0.0


def calculate_style_dict_similarity(base_dict: dict, eval_dict: dict) -> float:
    """Calculate a normalized similarity (0.0-1.0) between two style/attribute dictionaries."""

    # Handle edge cases
    if (base_dict and not eval_dict) or (not base_dict and eval_dict):
        return 0.0
    if not base_dict and not eval_dict:
        return 1.0

    # Union of all keys
    all_keys = set(base_dict) | set(eval_dict)
    total_bits = len(all_keys)

    # Count matched bits
    matched_bits = sum(1 for key in all_keys if base_dict.get(key) == eval_dict.get(key))

    return matched_bits / total_bits


def calculate_total_iou_score(bboxes1: list[BoundingBox], bboxes2: list[BoundingBox]) -> float:
    """Calculate total IoU score between two lists of bounding boxes."""

    if len(bboxes1) == 0 or len(bboxes2) == 0:
        return 0.0

    b1 = np.array(bboxes1, dtype=np.float32)  # (N,4)
    b2 = np.array(bboxes2, dtype=np.float32)  # (M,4)

    # Calculate origin for each bbox list separately using min x and y
    origin1 = np.array([b1[:, 0].min(), b1[:, 1].min()], dtype=np.float32)
    origin2 = np.array([b2[:, 0].min(), b2[:, 1].min()], dtype=np.float32)

    # Normalize centers relative to their respective origins
    b1[:, 0:2] -= origin1
    b2[:, 0:2] -= origin2

    # Compute corners assuming (x,y) is top-left
    b1_min = b1[:, :2]  # (N,2)
    b1_max = b1[:, :2] + b1[:, 2:4]  # (N,2)
    b2_min = b2[:, :2]  # (M,2)
    b2_max = b2[:, :2] + b2[:, 2:4]  # (M,2)

    # Expand dimensions to broadcast and compute intersection
    inter_min = np.maximum(b1_min[:, None, :], b2_min[None, :, :])  # (N,M,2)
    inter_max = np.minimum(b1_max[:, None, :], b2_max[None, :, :])  # (N,M,2)
    inter_wh = np.clip(inter_max - inter_min, 0, None)  # (N,M,2)
    inter_area = inter_wh[:, :, 0] * inter_wh[:, :, 1]  # (N,M)

    # Total intersection
    total_inter = inter_area.sum()

    # Total area
    area1 = (b1[:, 2] * b1[:, 3]).sum()
    area2 = (b2[:, 2] * b2[:, 3]).sum()
    total_union = area1 + area2 - total_inter

    return float(total_inter / total_union) if total_union > 0 else 0.0


def build_shape_iou_matrix(
    b1: list[BoundingBox], b2: list[BoundingBox], origin: tuple[BoundingBox, BoundingBox] = None
) -> np.ndarray:
    """Calculate IoU matrix based on box size only (ignore position) between two lists of bounding boxes."""

    b1 = np.array(b1, dtype=np.float32)  # (N, 4)
    b2 = np.array(b2, dtype=np.float32)  # (M, 4)

    if origin is not None:
        b1[:, 0:2] -= np.array(origin[0], dtype=np.float32)[0:2]  # (4,)
        b2[:, 0:2] -= np.array(origin[1], dtype=np.float32)[0:2]  # (4,)

    # Compute half sizes
    half_b1 = b1[:, 2:4] / 2  # (N, 2)
    half_b2 = b2[:, 2:4] / 2  # (M, 2)

    # Expand dimensions to broadcast and compute intersection on size only (ignore position)
    inter_min = np.maximum(-half_b1[:, None, :], -half_b2[None, :, :])  # (N, M, 2)
    inter_max = np.minimum(half_b1[:, None, :], half_b2[None, :, :])  # (N, M, 2)
    inter_wh = np.clip(inter_max - inter_min, 0, None)  # (N, M, 2)
    inter_area = inter_wh[:, :, 0] * inter_wh[:, :, 1]  # (N, M)

    area1 = b1[:, 2] * b1[:, 3]  # (N,)
    area2 = b2[:, 2] * b2[:, 3]  # (M,)
    union = area1[:, None] + area2[None, :] - inter_area  # (N, M)

    iou_matrix = np.where(union > 0, inter_area / union, 0)
    return iou_matrix


def build_position_sim_matrix(
    b1: list[BoundingBox],
    b2: list[BoundingBox],
    diagonal: float,
    origin: tuple[BoundingBox, BoundingBox] = None,
) -> np.ndarray:
    """
    Build position similarity matrix between two lists of bounding boxes based on distance.
    Returns an (N, M) matrix of similarities where N = len(b1) and M = len(b2).
    """
    b1 = np.array(b1, dtype=np.float32)  # (N, 4)
    b2 = np.array(b2, dtype=np.float32)  # (M, 4)

    if origin is not None:
        b1[:, 0:2] -= np.array(origin[0], dtype=np.float32)[0:2]  # (4,)
        b2[:, 0:2] -= np.array(origin[1], dtype=np.float32)[0:2]  # (4,)

    centers1 = b1[:, :2] + b1[:, 2:] / 2  # (N, 2)
    centers2 = b2[:, :2] + b2[:, 2:] / 2  # (M, 2)

    # Compute full pairwise distances to get an (N, M) similarity matrix
    deltas = centers1[:, None, :] - centers2[None, :, :]  # (N, M, 2)
    distances = np.linalg.norm(deltas, axis=2)  # (N, M)

    pos_sim_matrix = np.where(
        distances < diagonal,
        1 - distances / diagonal,
        0,
    )

    return pos_sim_matrix


def build_text_sim_matrix(base_texts: list[str], eval_texts: list[str]) -> np.ndarray:
    """
    Match texts across two dictionaries using cosine similarity. Returns pairs of total best matching indices.
    """

    # Repalce empty texts with placeholder to avoid issues with vectorizer and similarity calculation
    base_texts = [text if text else "§§§§§" for text in base_texts]
    eval_texts = [text if text else "§§§§§" for text in eval_texts]

    # Get size of base texts
    base_texts_size = len(base_texts)

    # Build character n-gram vectors and cosine similarity matrix
    ngram_matrix = CountVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(base_texts + eval_texts)
    sim_matrix = cosine_similarity(ngram_matrix[:base_texts_size], ngram_matrix[base_texts_size:])

    return sim_matrix


def measure_incremental_coverage(goal_text, original_text, updated_text, analyzer="word", ngram_range=(1, 2)):
    """
    Measure the incremental coverage of updated_text over original_text with respect to goal_text, based on n-gram overlap.
    """

    # Handle edge cases
    if goal_text == updated_text:
        return 1.0

    texts = [goal_text, original_text, updated_text]
    try:
        ngram_matrix = CountVectorizer(analyzer=analyzer, ngram_range=ngram_range, binary=True).fit_transform(texts)
    except ValueError:
        # If the text is too short for the specified n-gram range, fallback to character n-grams
        ngram_matrix = CountVectorizer(analyzer="char_wb", ngram_range=(3, 5), binary=True).fit_transform(texts)

    goal_ngram_vector = ngram_matrix[0].toarray()[0]
    original_ngram_vector = ngram_matrix[1].toarray()[0]
    updated_ngram_vector = ngram_matrix[2].toarray()[0]

    target_total = np.sum(goal_ngram_vector)
    if target_total == 0:
        return 0

    # ngrams newly introduced by addition
    new_ngrams = (updated_ngram_vector - original_ngram_vector) > 0

    # among those, which overlap target?
    new_overlap = np.sum(new_ngrams & (goal_ngram_vector > 0))

    # coverage of target by newly introduced ngrams
    new_coverage = new_overlap / target_total

    return new_coverage


def find_best_pairwise_matches(
    sim_matrix: np.ndarray,
    cur_pairwise_indices: list[tuple[int, int]] = None,
    threshold: float = 0.5,
) -> list[tuple[int, int]]:
    """Get best one-to-one matches above threshold, excluding existing pairwise indices."""

    if sim_matrix.size == 0:
        return []

    n_rows, n_cols = sim_matrix.shape
    cur_pairwise_indices = cur_pairwise_indices or []

    # Exclude rows/cols already used by current matches.
    used_rows = {i for i, j in cur_pairwise_indices if 0 <= i < n_rows and 0 <= j < n_cols}
    used_cols = {j for i, j in cur_pairwise_indices if 0 <= i < n_rows and 0 <= j < n_cols}

    remaining_rows = [i for i in range(n_rows) if i not in used_rows]
    remaining_cols = [j for j in range(n_cols) if j not in used_cols]

    if not remaining_rows or not remaining_cols:
        return []

    sub = sim_matrix[np.ix_(remaining_rows, remaining_cols)]

    # Single-row / single-col fast paths
    r, c = sub.shape
    if r == 1:
        j_sub = int(np.argmax(sub[0]))
        score = sub[0, j_sub]
        return [(remaining_rows[0], remaining_cols[j_sub])] if score >= threshold else []

    if c == 1:
        i_sub = int(np.argmax(sub[:, 0]))
        score = sub[i_sub, 0]
        return [(remaining_rows[i_sub], remaining_cols[0])] if score >= threshold else []

    # Hungarian assignment on remaining candidates
    row_idx, col_idx = linear_sum_assignment(1.0 - sub)

    new_matches: list[tuple[int, int]] = []
    for i_sub, j_sub in zip(row_idx, col_idx):
        if sub[i_sub, j_sub] >= threshold:
            new_matches.append((remaining_rows[i_sub], remaining_cols[j_sub]))

    return new_matches
