"""Module for evaluating DOM element matching between snapshots."""

import math
from typing import TypeAlias

import numpy as np

from metrics.utils.typings import (
    BoundingBox,
    ModuleElement,
    NodeElement,
    PageElements,
    ComparisonResults,
)
from metrics.utils.dom_utils import (
    concat_text_fragments,
    compute_enclosing_bbox,
)
from metrics.utils.metric_utils import (
    calculate_total_iou_score,
    calculate_color_similarity,
    build_shape_iou_matrix,
    build_position_sim_matrix,
    build_text_sim_matrix,
    find_best_pairwise_matches,
    measure_incremental_coverage,
)

ModuleScore: TypeAlias = tuple[str, str, float, float, float]
NodeScore: TypeAlias = tuple[str, str, float, float]


def _pick_keys(d: dict, keys: list[str]) -> dict:
    """Filter a dictionary to only include specified keys."""
    return {k: d[k] for k in keys if k in d}


def _get_idx_map(ids: list[str]) -> dict[str, int]:
    """Helper function to create a mapping from ID to index for quick lookups."""
    return {id_: idx for idx, id_ in enumerate(ids)}


def _collect_data_from_modules(modules: dict[str, ModuleElement]):
    """Collect parallel lists of element IDs, normalized texts, and bounding boxes."""

    ids: list[str] = []
    texts: list[str] = []
    bboxes: list[BoundingBox] = []

    for meta_id, module in modules.items():
        ids.append(meta_id)
        texts.append(module.text)
        bboxes.append(module.bbox)

    return ids, texts, bboxes


def _collect_data_from_text_nodes(nodes: dict[str, NodeElement]):
    """Collect parallel lists of element IDs, normalized texts, and bounding box groups."""

    ids: list[str] = []
    texts: list[str] = []
    bbox_groups: list[list[BoundingBox]] = []

    for meta_id, node in nodes.items():
        ids.append(meta_id)
        texts.append(node.text)
        bbox_groups.append(node.bboxes)

    return ids, texts, bbox_groups


def _collect_data_from_sign_nodes(nodes: dict[str, NodeElement]):
    """Collect parallel lists of element IDs and bounding boxes."""

    ids: list[str] = list(nodes)
    bboxes: list[BoundingBox] = [node.bboxes[0] for node in nodes.values()]

    return ids, bboxes


def _collect_node_for_fuzzy_matching(module_ids: list[str], page_elements: PageElements, is_deep_collection: bool):
    """Collect parallel lists of element IDs, normalized texts, and bounding boxes."""
    ids: list[str] = []
    texts: list[str] = []
    bboxes: list[BoundingBox] = []

    for module_id in module_ids:
        module = page_elements.modules[module_id]

        if not is_deep_collection:
            ids.append(module_id)
            texts.append(module.text)
            bboxes.append(module.bbox)
            continue

        for node_id in module.leaf_texts:
            node = page_elements.nodes[node_id]
            ids.append(module_id)
            texts.append(node.text)
            bboxes.append(compute_enclosing_bbox(node.bboxes))
    return ids, texts, bboxes


def _init_pairs_indices(
    previous_id_matches: list[tuple[str, str]],
    base_elems: dict[str, ModuleElement | NodeElement],
    eval_elems: dict[str, ModuleElement | NodeElement],
) -> list[tuple[int, int]]:
    """Return non-conflicting index pairs from previous_matches.

    For each (base_id, eval_id) in previous_matches, if both IDs exist in the current
    base/eval id lists and neither corresponding index is already used by current_matches,
    include the (base_idx, eval_idx) pair. Marks indices as used when added to ensure
    one-to-one matching and preserves the order of previous_matches.
    """
    if not previous_id_matches:
        return []

    # Fast lookup from id -> index
    base_idx_by_id = {bid: idx for idx, bid in enumerate(base_elems.keys())}
    eval_idx_by_id = {eid: idx for idx, eid in enumerate(eval_elems.keys())}

    new_pairs: list[tuple[int, int]] = []
    for base_id, eval_id in previous_id_matches:
        b_idx = base_idx_by_id.get(base_id)
        e_idx = eval_idx_by_id.get(eval_id)
        # skip if ids don't exist in this resolution
        if b_idx is None or e_idx is None:
            continue
        # preserve the order of previous_matches by appending valid pairs
        new_pairs.append((b_idx, e_idx))

    return new_pairs


def _find_module_matches(
    base_page_elements: PageElements,
    eval_page_elements: PageElements,
    screen_diagonal: float,
    pre_module_ids: list[tuple[str, str]] = None,
    disable_merge: bool = False,
) -> list[ModuleScore]:
    """Match module elements between base and evaluation snapshots."""

    # Return empty if no modules present
    if len(base_page_elements.modules) == 0 or len(eval_page_elements.modules) == 0:
        return []

    # Collect IDs, texts, and bounding boxes
    base_ids, base_texts, base_bboxes = _collect_data_from_modules(base_page_elements.modules)
    eval_ids, eval_texts, eval_bboxes = _collect_data_from_modules(eval_page_elements.modules)

    # Build similarity matrices
    text_sim_matrix = build_text_sim_matrix(base_texts, eval_texts)
    shape_iou_matrix = build_shape_iou_matrix(base_bboxes, eval_bboxes)
    position_sim_matrix = build_position_sim_matrix(base_bboxes, eval_bboxes, screen_diagonal)
    overall_score_matrix = text_sim_matrix * 0.5 + shape_iou_matrix * 0.3 + position_sim_matrix * 0.2

    # First, take all non-conflicting pairs from previous matches with a lenient threshold to preserve continuity and order
    matched_pairs_indices = _init_pairs_indices(pre_module_ids, base_page_elements.modules, eval_page_elements.modules)
    # Find best pairwise matches for unmatched items, excluding already matched indices from previous matches
    matched_pairs_indices += find_best_pairwise_matches(overall_score_matrix, matched_pairs_indices)

    # Compile matched results
    module_matches: list[ModuleScore] = [
        (
            base_ids[base_idx],
            eval_ids[eval_idx],
            text_sim_matrix[base_idx, eval_idx],
            shape_iou_matrix[base_idx, eval_idx],
            position_sim_matrix[base_idx, eval_idx],
        )
        for base_idx, eval_idx in matched_pairs_indices
    ]

    # If merging is disabled, return early with initial matches without any merging logic applied
    if disable_merge:
        return module_matches

    # First: Merge unmatched modules with neighboring matched modules to improve scores
    _merge_adjacent_module_pairs(
        base_page_elements.modules,
        (base_ids, base_texts, base_bboxes),
        (eval_ids, eval_texts, eval_bboxes),
        module_matches,
        screen_diagonal,
        primary_match_index=0,
    )
    _merge_adjacent_module_pairs(
        eval_page_elements.modules,
        (eval_ids, eval_texts, eval_bboxes),
        (base_ids, base_texts, base_bboxes),
        module_matches,
        screen_diagonal,
        primary_match_index=1,
    )

    # Second: Merge unmatched modules with fuzzy matching to improve recall
    _merge_unmatched_module_pairs(
        base_page_elements,
        eval_page_elements,
        module_matches,
        screen_diagonal,
    )

    return module_matches


def _merge_unmatched_module_pairs(
    base_page_elements: PageElements,
    eval_page_elements: PageElements,
    module_matches: list[ModuleScore],
    screen_diagonal: int,
) -> None:
    """Find remaining unmatched primary modules and attempt to merge them with secondary modules
    via fuzzy (leaf-node-level) matching to improve recall."""

    # Build lookup: which primary/secondary module IDs are already matched
    base_matched_ids: set[str] = {m[0] for m in module_matches}
    eval_matched_ids: set[str] = {m[1] for m in module_matches}

    base_unmatched_ids = [x for x in base_page_elements.modules if x not in base_matched_ids]
    eval_unmatched_ids = [x for x in eval_page_elements.modules if x not in eval_matched_ids]
    if not base_unmatched_ids or not eval_unmatched_ids:
        return

    # Run fuzzy matching at leaf-node level to find merge candidates
    fuzzy_merge_candidates = _generate_fuzzy_match_pairs(
        base_page_elements, eval_page_elements, base_unmatched_ids, eval_unmatched_ids, screen_diagonal
    )
    if not fuzzy_merge_candidates:
        return

    # Apply merge records to module_matches in-place
    _apply_fuzzy_merging(
        fuzzy_merge_candidates, base_page_elements, eval_page_elements, module_matches, screen_diagonal
    )


def _generate_fuzzy_match_pairs(
    primary_page_elements: PageElements,
    secondary_page_elements: PageElements,
    primary_unmatched_ids: list[str],
    secondary_unmatched_ids: list[str],
    screen_diagonal: int,
) -> list[tuple[str, str]]:
    """Run leaf-node-level fuzzy matching between unmatched primary modules and all secondary modules.

    Returns a list of (primary_module_id, secondary_module_id) pairs deduplicated and
    ordered by first occurrence.
    """

    # Determine whether to conduct in-depth collection based on the number of unmatched items.
    is_deep_collection = len(primary_unmatched_ids) == 1 or len(secondary_unmatched_ids) == 1

    primary_module_ids, primary_node_texts, primary_node_bboxes = _collect_node_for_fuzzy_matching(
        primary_unmatched_ids, primary_page_elements, is_deep_collection
    )
    secondary_module_ids, secondary_node_texts, secondary_node_bboxes = _collect_node_for_fuzzy_matching(
        secondary_unmatched_ids, secondary_page_elements, is_deep_collection
    )

    if not primary_module_ids or not secondary_module_ids:
        return []

    # Build similarity matrices at leaf-node level
    text_sim_matrix = build_text_sim_matrix(primary_node_texts, secondary_node_texts)
    shape_iou_matrix = build_shape_iou_matrix(primary_node_bboxes, secondary_node_bboxes)
    position_sim_matrix = build_position_sim_matrix(primary_node_bboxes, secondary_node_bboxes, screen_diagonal)
    overall_score_matrix = text_sim_matrix * 0.5 + shape_iou_matrix * 0.3 + position_sim_matrix * 0.2

    matched_pairs_indices = find_best_pairwise_matches(overall_score_matrix, threshold=0.1)

    # Build merge records — deduplicate while preserving first-occurrence order
    seen: set[tuple[str, str]] = set()
    merge_records: list[tuple[str, str]] = []
    for primary_node_idx, secondary_node_idx in matched_pairs_indices:
        pair = (primary_module_ids[primary_node_idx], secondary_module_ids[secondary_node_idx])
        if pair not in seen:
            seen.add(pair)
            merge_records.append(pair)

    return merge_records


def _apply_fuzzy_merging(
    fuzzy_merge_candidates: list[tuple[str, str]],
    base_page_elements: PageElements,
    eval_page_elements: PageElements,
    module_matches: list[ModuleScore],
    screen_diagonal: int,
) -> None:
    """Apply fuzzy merge records to module_matches in-place.

    For each candidate (base_module_id, eval_module_id):
    - If base_module_id was already seen: merge the new eval module into the
      previously matched eval module and recalculate scores.
    - If eval_module_id was already seen: merge the new base module into the
      previously matched base module and recalculate scores.
    - Otherwise: append a new match record and register both IDs for future merges.
    """
    # Track seen IDs: module_id -> (match_index, paired_module_id)
    seen_base: dict[str, tuple[int, str]] = {}
    seen_eval: dict[str, tuple[int, str]] = {}

    for base_id, eval_id in fuzzy_merge_candidates:

        if base_id not in base_page_elements.modules or eval_id not in eval_page_elements.modules:
            continue

        if base_id in seen_base:
            match_idx, paired_eval_id = seen_base[base_id]
            anchor = eval_page_elements.modules[paired_eval_id]  # module to extend
            extra = eval_page_elements.modules[eval_id]  # module to absorb
            ref_text = base_page_elements.modules[base_id].text
            ref_bbox = base_page_elements.modules[base_id].bbox
            absorb_from = (eval_page_elements.modules, eval_id)

        elif eval_id in seen_eval:
            match_idx, paired_base_id = seen_eval[eval_id]
            anchor = base_page_elements.modules[paired_base_id]  # module to extend
            extra = base_page_elements.modules[base_id]  # module to absorb
            ref_text = eval_page_elements.modules[eval_id].text
            ref_bbox = eval_page_elements.modules[eval_id].bbox
            absorb_from = (base_page_elements.modules, base_id)

        else:
            match_idx = None
            anchor = base_page_elements.modules[base_id]
            extra = None
            ref_text = eval_page_elements.modules[eval_id].text
            ref_bbox = eval_page_elements.modules[eval_id].bbox
            absorb_from = None

        # Compute merged state for score check (without mutating yet)
        merged_text = concat_text_fragments([anchor.text, extra.text]) if extra else anchor.text
        merged_bbox = compute_enclosing_bbox([anchor.bbox, extra.bbox]) if extra else anchor.bbox
        original_text = anchor.text if extra else ""

        new_scores = _get_merge_score(
            (ref_text, merged_text),
            (ref_bbox, merged_bbox),
            original_text,
            screen_diagonal,
        )
        if new_scores is None:
            continue

        # Score improves — apply mutations
        if extra is not None:
            anchor.text = merged_text
            anchor.bbox = merged_bbox
            anchor.leaf_texts += extra.leaf_texts
            anchor.leaf_signs += extra.leaf_signs
            del absorb_from[0][absorb_from[1]]
        else:
            # New match — register and append placeholder
            match_idx = len(module_matches)
            module_matches.append((base_id, eval_id, 0.0, 0.0, 0.0))
            seen_base[base_id] = (match_idx, eval_id)
            seen_eval[eval_id] = (match_idx, base_id)

        base_id, eval_id = module_matches[match_idx][:2]
        module_matches[match_idx] = (base_id, eval_id, *new_scores)


def _merge_adjacent_module_pairs(
    primary_modules: dict[str, ModuleElement],
    primary_module_data: tuple[list[str], list[str], list[BoundingBox]],
    secondary_module_data: tuple[list[str], list[str], list[BoundingBox]],
    module_matches: list[ModuleScore],
    screen_diagonal: float,
    primary_match_index: int,  # 0 for base, 1 for eval
):
    """Attempt to merge unmatched primary-side modules with matched ones based on
    text similarity and bounding box proximity.

    For each matched module, keep absorbing adjacent unmatched neighbors as long as
    the score keeps improving. Only move to the next matched module when no neighbor
    can improve the score further.
    """
    secondary_match_index = 1 - primary_match_index  # 0 -> 1, 1 -> 0

    primary_idx_map = _get_idx_map(primary_module_data[0])
    secondary_idx_map = _get_idx_map(secondary_module_data[0])

    # Early exit: nothing to absorb if all primary modules are already matched
    matched_primary_ids = {m[primary_match_index] for m in module_matches}
    if matched_primary_ids.issuperset(primary_module_data[0]):
        return

    # Iterate over each matched module and try to absorb neighbors until exhausted
    for match_idx, match in enumerate(module_matches):
        matched_id = match[primary_match_index]
        secondary_id = match[secondary_match_index]

        if matched_id not in primary_idx_map or secondary_id not in secondary_idx_map:
            continue

        secondary_idx = secondary_idx_map.get(secondary_id)
        if secondary_idx is None:
            continue

        goal_text = secondary_module_data[1][secondary_idx]
        goal_bbox = secondary_module_data[2][secondary_idx]

        # Keep absorbing neighbors of this matched module until no improvement
        while True:
            matched_ids = {m[primary_match_index] for m in module_matches}
            matched_idx = primary_idx_map[matched_id]

            neighbor = _find_best_neighbor_merge_data(primary_module_data, matched_ids, matched_idx)
            if neighbor is None:
                break  # no unmatched neighbor in either direction

            cur_id, cur_idx, original_text, merged_text, merged_box = neighbor

            merge_scores = _get_merge_score(
                (goal_text, merged_text),
                (goal_bbox, merged_box),
                original_text,
                screen_diagonal,
            )
            if not merge_scores:
                break  # neighbor found but no improvement — stop expanding this matched module

            module_matches[match_idx] = module_matches[match_idx][:2] + merge_scores
            primary_modules[matched_id].text = merged_text
            primary_modules[matched_id].bbox = merged_box
            primary_modules[matched_id].leaf_texts += primary_modules[cur_id].leaf_texts
            primary_modules[matched_id].leaf_signs += primary_modules[cur_id].leaf_signs

            _prune_merge_data(primary_module_data, merged_text, merged_box, cur_idx, matched_idx)
            del primary_modules[cur_id]

            # Rebuild index map after deletion — matched_id index may have shifted
            primary_idx_map = _get_idx_map(primary_module_data[0])


def _find_best_neighbor_merge_data(
    module_data: tuple[list[str], list[str], list[BoundingBox]],
    matched_ids: set[str],
    matched_idx: int,
) -> tuple[str, int, str, str, BoundingBox] | None:
    """Find the nearest unmatched neighbor of matched_idx, preferring left over right.

    Returns (cur_id, cur_idx, original_text, merged_text, merged_bbox),
    or None if no unmatched neighbor exists in either direction.
    Text order follows positional order: the module that appears first (lower index) comes first.
    """
    ids, texts, bboxes = module_data

    for step in [-1, 1]:
        neighbor_idx = matched_idx + step
        while 0 <= neighbor_idx < len(ids):
            if ids[neighbor_idx] not in matched_ids:
                cur_id = ids[neighbor_idx]
                original_text = texts[matched_idx]

                if neighbor_idx < matched_idx:
                    # Unmatched is to the left — its text comes first
                    merged_text = concat_text_fragments([texts[neighbor_idx], texts[matched_idx]])
                    merged_bbox = compute_enclosing_bbox([bboxes[neighbor_idx], bboxes[matched_idx]])
                else:
                    # Unmatched is to the right — matched text comes first
                    merged_text = concat_text_fragments([texts[matched_idx], texts[neighbor_idx]])
                    merged_bbox = compute_enclosing_bbox([bboxes[matched_idx], bboxes[neighbor_idx]])

                return cur_id, neighbor_idx, original_text, merged_text, merged_bbox
            neighbor_idx += step

    return None


def _prune_merge_data(
    module_data: tuple[list[str], list[str], list[BoundingBox]],
    merged_text: str,
    merged_box: BoundingBox,
    cur_idx: int,
    neighbor_idx: int,
):
    """Remove the unmatched module's data and update the neighboring matched module's data
    with the merged results after a successful merge."""

    ids, texts, bboxes = module_data

    # Update the neighbor's data with merged results
    texts[neighbor_idx] = merged_text
    bboxes[neighbor_idx] = merged_box

    # Remove the current unmatched module's data as it has been merged
    # Adjust neighbor_idx if cur_idx comes before it to account for the shifted index after deletion
    del ids[cur_idx]
    del texts[cur_idx]
    del bboxes[cur_idx]


def _get_merge_score(
    comparison_text: tuple[str, str],
    comparison_bbox: tuple[BoundingBox, BoundingBox],
    original_text: str,
    screen_diagonal,
):
    """Determine if merging an unmatched base module with a neighboring matched module improves the overall score."""

    goal_text, merged_text = comparison_text
    goal_bbox, merged_bbox = comparison_bbox

    # Calculate incremental coverage
    coverage_improvement = measure_incremental_coverage(goal_text, original_text, merged_text)
    if coverage_improvement < 0:
        return None  # merged text is less similar to the goal text than the original text — reject this merge

    # Calculate text similarity and bounding box proximity
    text_sim = build_text_sim_matrix([goal_text], [merged_text])[0, 0]
    shape_sim = build_shape_iou_matrix([goal_bbox], [merged_bbox])[0, 0]
    position_sim = build_position_sim_matrix([goal_bbox], [merged_bbox], screen_diagonal)[0, 0]

    return text_sim, shape_sim, position_sim  # Return new scores if merge is an improvement


def _find_text_node_matches(
    base_nodes: dict[str, NodeElement],
    eval_nodes: dict[str, NodeElement],
    pre_node_ids: list[tuple[str, str]] = None,
) -> list[NodeScore]:
    """Match text node elements between base and evaluation snapshots."""

    # Return empty if no nodes present
    if len(base_nodes) == 0 or len(eval_nodes) == 0:
        return []

    # Collect IDs, texts, and bounding boxe groups
    base_ids, base_texts, base_box_groups = _collect_data_from_text_nodes(base_nodes)
    eval_ids, eval_texts, eval_box_groups = _collect_data_from_text_nodes(eval_nodes)

    # Build similarity matrices
    text_sim_matrix = build_text_sim_matrix(base_texts, eval_texts)

    # First, take all non-conflicting pairs from previous matches with a lenient threshold to preserve continuity and order
    matched_pairs_indices = _init_pairs_indices(pre_node_ids, base_nodes, eval_nodes)
    # Find best pairwise matches for unmatched items, excluding already matched indices from previous matches
    matched_pairs_indices += find_best_pairwise_matches(text_sim_matrix, matched_pairs_indices)

    # Compile matched results
    node_matches: list[NodeScore] = []
    for base_idx, eval_idx in matched_pairs_indices:
        base_id = base_ids[base_idx]
        eval_id = eval_ids[eval_idx]
        base_color = base_nodes[base_id].style.get("color")
        eval_color = eval_nodes[eval_id].style.get("color")
        color_similarity = calculate_color_similarity(base_color, eval_color) if base_color and eval_color else 0.0
        total_iou_score = calculate_total_iou_score(base_box_groups[base_idx], eval_box_groups[eval_idx])
        node_match = (
            base_id,
            eval_id,
            total_iou_score,
            text_sim_matrix[base_idx, eval_idx],
            color_similarity,
        )
        node_matches.append(node_match)

    return node_matches


def _find_sign_node_matches(
    base_nodes: dict[str, NodeElement],
    eval_nodes: dict[str, NodeElement],
    module_bbox: tuple[BoundingBox, BoundingBox],
    pre_node_ids: list[tuple[str, str]] = None,
) -> list[NodeScore]:
    """Match sign node elements between base and evaluation snapshots."""

    # Return empty if no nodes present
    if len(base_nodes) == 0 or len(eval_nodes) == 0:
        return []

    # Collect IDs, texts, and bounding boxe groups
    base_ids, base_bboxes = _collect_data_from_sign_nodes(base_nodes)
    eval_ids, eval_bboxes = _collect_data_from_sign_nodes(eval_nodes)

    # Adopt diagonal based on element sizes
    diagonal = max(math.hypot(*(module_bbox[0][2:])), math.hypot(*(module_bbox[1][2:])))

    # Build similarity matrices
    shape_iou_matrix = build_shape_iou_matrix(base_bboxes, eval_bboxes, module_bbox)
    position_sim_matrix = build_position_sim_matrix(base_bboxes, eval_bboxes, diagonal, module_bbox)
    overall_score_matrix = shape_iou_matrix * 0.5 + position_sim_matrix * 0.5

    # First, take all non-conflicting pairs from previous matches with a lenient threshold to preserve continuity and order
    matched_pairs_indices = _init_pairs_indices(pre_node_ids, base_nodes, eval_nodes)
    # Find best pairwise matches for unmatched items, excluding already matched indices from previous matches
    matched_pairs_indices += find_best_pairwise_matches(overall_score_matrix, matched_pairs_indices)

    # Compile matched results
    node_matches: list[NodeScore] = []
    for base_idx, eval_idx in matched_pairs_indices:
        base_id = base_ids[base_idx]
        eval_id = eval_ids[eval_idx]
        base_style = base_nodes[base_id].style
        eval_style = eval_nodes[eval_id].style
        text_similarity = 1.0 if base_nodes[base_id].text == eval_nodes[eval_id].text else 0.0
        base_color = base_style.get("color") or eval_style.get("background-color")
        eval_color = eval_style.get("color") or base_style.get("background-color")
        color_similarity = calculate_color_similarity(base_color, eval_color) if base_color and eval_color else 0.0

        total_iou_score = calculate_total_iou_score(base_nodes[base_id].bboxes, eval_nodes[eval_id].bboxes)
        node_match = (
            base_id,
            eval_id,
            total_iou_score,
            text_similarity,
            color_similarity,
        )
        node_matches.append(node_match)

    return node_matches


def _aggregate_module_area(modules: dict[str, ModuleElement], matched_ids: list[str]) -> tuple[float, float]:
    """Calculate total area of matched and unmatched modules based on their bounding boxes."""
    matched_id_set = set(matched_ids)
    matched = sum(m.bbox[2] * m.bbox[3] for k, m in modules.items() if k in matched_id_set)
    unmatched = sum(m.bbox[2] * m.bbox[3] for k, m in modules.items() if k not in matched_id_set)
    return matched, unmatched


def _aggregate_node_area(nodes: dict[str, NodeElement], matched_ids: list[str]) -> tuple[float, float]:
    """Calculate total area of matched and unmatched nodes based on their bounding boxes."""
    matched_id_set = set(matched_ids)
    matched = sum(sum(b[2] * b[3] for b in n.bboxes) for k, n in nodes.items() if k in matched_id_set)
    unmatched = sum(sum(b[2] * b[3] for b in n.bboxes) for k, n in nodes.items() if k not in matched_id_set)
    return matched, unmatched


def _summarize_module_matches(base_elems: PageElements, eval_elems: PageElements, module_matches: list[ModuleScore]):
    """Summarize match counts and average scores for modules."""
    if not module_matches:
        return {
            "tp": 0,
            "fn": len(base_elems.modules),
            "fp": len(eval_elems.modules),
            "coverage": 0.0,
            "text_score": 0.0,
            "shape_score": 0.0,
            "position_score": 0.0,
        }

    base_ids, eval_ids, text_scores, shape_scores, position_scores = (
        zip(*module_matches) if module_matches else ([], [], [], [], [])
    )

    # Calculate coverage based on total area of matched vs unmatched modules
    base_matched, base_unmatched = _aggregate_module_area(base_elems.modules, base_ids)
    eval_matched, eval_unmatched = _aggregate_module_area(eval_elems.modules, eval_ids)
    matched_size = base_matched + eval_matched
    unmatched_size = base_unmatched + eval_unmatched
    total_size = matched_size + unmatched_size
    coverage = matched_size / total_size if total_size > 0 else 0.0

    module_stats = {
        "tp": len(module_matches),
        "fn": len(base_elems.modules) - len(module_matches),
        "fp": len(eval_elems.modules) - len(module_matches),
        "coverage": coverage,
        "text_score": np.mean(text_scores) if text_scores else 0.0,
        "shape_score": np.mean(shape_scores) if shape_scores else 0.0,
        "position_score": np.mean(position_scores) if position_scores else 0.0,
    }
    return module_stats


def _summarize_node_matches(base_elems: PageElements, eval_elems: PageElements, node_matches: list[NodeScore]):
    """Summarize match counts and average scores for nodes."""

    if not node_matches:
        return {
            "tp": 0,
            "fn": len(base_elems.nodes),
            "fp": len(eval_elems.nodes),
            "coverage": 0.0,
            "iou_score": 0.0,
            "text_score": 0.0,
            "color_score": 0.0,
        }

    base_ids, eval_ids, iou_scores, text_scores, color_scores = zip(*node_matches)

    # Calculate coverage based on total area of matched vs unmatched nodes
    base_matched, base_unmatched = _aggregate_node_area(base_elems.nodes, base_ids)
    eval_matched, eval_unmatched = _aggregate_node_area(eval_elems.nodes, eval_ids)
    matched_size = base_matched + eval_matched
    unmatched_size = base_unmatched + eval_unmatched
    total_size = matched_size + unmatched_size
    coverage = matched_size / total_size if total_size > 0 else 0.0

    node_stats = {
        "tp": len(node_matches),
        "fn": len(base_elems.nodes) - len(node_matches),
        "fp": len(eval_elems.nodes) - len(node_matches),
        "coverage": coverage,
        "iou_score": np.mean(iou_scores) if iou_scores else 0.0,
        "text_score": np.mean(text_scores) if text_scores else 0.0,
        "color_score": np.mean(color_scores) if color_scores else 0.0,
    }
    return node_stats


def evaluate(
    base_elems: PageElements,
    eval_elems: PageElements,
    resolution_str: str,
    pre_module_ids: list[tuple[str, str]] = None,
    pre_node_ids: list[tuple[str, str]] = None,
    disable_merge: bool = False,
) -> ComparisonResults:
    """Evaluate DOM element matching between base and evaluation snapshots."""

    # Calculate screen diagonal
    diagonal = math.hypot(*tuple(map(int, resolution_str.split("x"))))

    # Match module elements
    module_matches = _find_module_matches(base_elems, eval_elems, diagonal, pre_module_ids, disable_merge)

    # Match node elements within matched modules
    node_matches: list[NodeScore] = []
    for module_match in module_matches:
        base_id, eval_id = module_match[0:2]

        base_module = base_elems.modules[base_id]
        eval_module = eval_elems.modules[eval_id]
        module_bboxes = (base_module.bbox, eval_module.bbox)

        # Match text nodes
        if base_module.leaf_texts and eval_module.leaf_texts:
            node_matches += _find_text_node_matches(
                _pick_keys(base_elems.nodes, base_module.leaf_texts),
                _pick_keys(eval_elems.nodes, eval_module.leaf_texts),
                pre_node_ids,
            )

        # Match sign nodes
        if base_module.leaf_signs and eval_module.leaf_signs:
            node_matches += _find_sign_node_matches(
                _pick_keys(base_elems.nodes, base_module.leaf_signs),
                _pick_keys(eval_elems.nodes, eval_module.leaf_signs),
                module_bboxes,
                pre_node_ids,
            )

    return ComparisonResults(
        module_stats=_summarize_module_matches(base_elems, eval_elems, module_matches),
        node_stats=_summarize_node_matches(base_elems, eval_elems, node_matches),
        module_ids=[m[0:2] for m in module_matches],
        node_ids=[n[0:2] for n in node_matches],
        source_elements=base_elems,
        generated_elements=eval_elems,
    )
