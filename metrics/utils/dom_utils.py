"""
Utility functions for DOM snapshot analysis using Playwright and CDP
"""

import re
from io import BytesIO
from PIL import Image
import numpy as np


from common.browser import Browser
from common.logger import common_logger
from metrics.utils.typings import (
    TEXT_NODE_TYPE,
    BoundingBox,
    DomSnapshotData,
    TreeNode,
    TextNode,
)

BOOL_ATTRIBUTES = {"checked", "selected", "disabled", "readonly", "multiple", "autofocus", "required"}

CALCULATE_DOCUMENT_BOUNDS = """
() => {
    const body = document.body
    const html = document.documentElement
    return [
        Math.max(body.scrollWidth, body.offsetWidth, html.scrollWidth, html.offsetWidth, html.clientWidth),
        Math.max(body.scrollHeight, body.offsetHeight, html.scrollHeight, html.offsetHeight, html.clientHeight)
    ]
}
"""


async def retrieve_snapshot_data(
    browser: Browser, url: str, resolution: tuple[int, int], computed_styles: list[str]
) -> DomSnapshotData:
    """Capture DOM snapshot using Playwright and CDP"""

    context = await browser.new_context(viewport={"width": resolution[0], "height": resolution[1]})
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded")

        # Inject fix CSS before capturing the DOM snapshot
        await page.add_style_tag(content="*{animation:none !important}")

        # Create a CDP session bound to this page and send analysis commands
        client = await context.new_cdp_session(page)
        snapshot = await client.send("DOMSnapshot.captureSnapshot", {"computedStyles": computed_styles})
        document = snapshot["documents"][0]

        # Calculate the full document bounds to determine the body bounding box
        [max_width, max_height] = await page.evaluate(CALCULATE_DOCUMENT_BOUNDS) or resolution

        return DomSnapshotData(
            nodes=document.get("nodes", {}),
            layout=document.get("layout", {}),
            text_boxes=document.get("textBoxes", {}),
            strings=snapshot.get("strings", []),
            resolution=resolution,
            body_bbox=(0, 0, max_width, max_height),
        )
    except Exception as exc:
        common_logger.error("Failed capture snapshot %s (%s): %s", url, resolution, exc)
        raise
    finally:
        await context.close()


async def retrieve_style_dict(browser: Browser, dom: DomSnapshotData, computed_styles: list[str]):
    """Create style mapping from backendNodeId to computed styles, excluding non-displayed elements"""
    nodes, strings = dom.nodes, dom.strings

    color_cache = {}

    async def _get_gradient_color(style_value: str) -> str:
        color = color_cache.get(style_value)
        if color is None:
            color = await extract_dominant_color(browser, style_value)
            color_cache[style_value] = color
        return color

    style_dict: dict[int, dict[str, str]] = {}
    for i, style_values in enumerate(dom.layout.get("styles", [])):
        node_idx = dom.layout.get("nodeIndex", [])[i]
        node_id = nodes.get("backendNodeId", [])[node_idx]
        node_style = {}
        for j, val_index in enumerate(style_values):
            style_name = computed_styles[j]
            style_value = strings[val_index]
            if is_transparent_color(style_value) or style_value == "0px" or style_value == "none":
                continue  # Skip transparent colors
            if style_name == "background-image" and "linear-gradient" in style_value:
                style_value = await _get_gradient_color(f"{style_name}: {style_value}")
                node_style["background-color"] = style_value
                continue  # Skip background-image if it's a gradient, use the computed color instead

            if style_name in {"background-image", "mask-image"} and style_value.startswith("url"):
                style_value = re.sub(r'url\(["\']?.*/([^/"\']+)["\']?\)', r"url(\1)", style_value)  # Normalize url(...)
            node_style[style_name] = style_value
        style_dict[node_id] = node_style

    # Retrieve body background color, default to white if not specified
    body_str_idx = strings.index("BODY") if "BODY" in strings else -1
    body_node_idx = nodes["nodeName"].index(body_str_idx) if body_str_idx != -1 else -1
    body_id = nodes.get("backendNodeId", [])[body_node_idx] if body_node_idx != -1 else None
    body_style = style_dict.get(body_id, {}) if body_id else {}
    body_background_color = body_style.get("background-color", "rgb(255, 255, 255)")

    # Mix with white if body background is transparent
    if body_background_color and body_background_color.startswith("rgba("):
        body_background_color = mix_color_with_background(body_background_color, "rgb(255, 255, 255)")

    # Covert all transparent colors to body background color to simplify analysis
    for node_id, styles in style_dict.items():
        for style_name, style_value in styles.items():
            if style_value.startswith("rgba("):
                styles[style_name] = mix_color_with_background(style_value, body_background_color)

    return style_dict


async def extract_dominant_color(browser: Browser, inline_style: str) -> str:
    """Retrieve the computed color value for a given style using Playwright rendering"""

    context = await browser.new_context()
    page = await context.new_page()

    try:
        # Create a temporary element with the specified style to compute its color
        await page.set_content(f'<html><body style="{inline_style}"></body></html>')
        screenshot = await page.screenshot(full_page=True)

        # Covert image to numpy array and extract the dominant color (simplified approach)
        img = Image.open(BytesIO(screenshot))
        arr = np.array(img)
        # Compute mean RGB values as a simple approximation of the dominant color
        mean_color = arr.mean(axis=(0, 1)).astype(int)
        return f"rgb({mean_color[0]}, {mean_color[1]}, {mean_color[2]})"
    except Exception as exc:
        common_logger.error("Failed to retrieve style color for %s: %s", inline_style, exc)
        raise
    finally:
        await context.close()


def mix_color_with_background(color: str, background: str) -> str:
    """Parse an rgba color string and blend it with the background color, returning a solid rgb color string."""
    try:
        color_match = re.match(r"rgba\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3}),\s*([01]?\.?\d*)\)", color)
        background_match = re.match(r"rgb\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})\)", background)
    except TypeError as exc:
        common_logger.error("Invalid color or background format: %s, %s. Error: %s", color, background, exc)
        raise exc

    if color_match and background_match:
        r_val, g_val, b_val, alpha = map(float, color_match.groups())
        r_bg, g_bg, b_bg = map(int, background_match.groups())
        blended_r = int(r_val * alpha + r_bg * (1 - alpha))
        blended_g = int(g_val * alpha + g_bg * (1 - alpha))
        blended_b = int(b_val * alpha + b_bg * (1 - alpha))
        return f"rgb({blended_r}, {blended_g}, {blended_b})"

    raise ValueError(f"Invalid color string format: {color}/{background}. Expected 'rgb(R,G,B)' or 'rgba(R,G,B,A)'.")


def create_attr_dict(dom: DomSnapshotData):
    """Create attribute mapping from backendNodeId to specific attribute value"""
    nodes, strings = dom.nodes, dom.strings

    # Page nodes
    ss_attributes = nodes.get("attributes", [])
    ss_backend_node_ids = nodes.get("backendNodeId", [])

    attr_dict = {}
    for idx, attrs in enumerate(ss_attributes):
        node_id = ss_backend_node_ids[idx]
        attr_dict[node_id] = {}
        for key_idx in range(0, len(attrs), 2):
            key_str_idx = attrs[key_idx]
            key_str = strings[key_str_idx]
            # Handle boolean attributes
            if key_str in BOOL_ATTRIBUTES:
                attr_dict[node_id][key_str] = True
                continue
            value_idx = attrs[key_idx + 1] if key_idx + 1 < len(attrs) else -1
            value_str = strings[value_idx] if value_idx != -1 else None
            if key_str and value_str:
                attr_dict[node_id][key_str] = value_str

    return attr_dict


def create_bbox_dict(dom: DomSnapshotData):
    """Create bounding box mapping from backendNodeId to bounding boxes"""
    nodes, layout = dom.nodes, dom.layout

    # Page layout and nodes
    ss_node_index = layout.get("nodeIndex", [])
    ss_layout_bounds = layout.get("bounds", [])
    ss_backend_node_ids = nodes.get("backendNodeId", [])

    bbox_dict: dict[str, BoundingBox] = {}
    for i, bbox in enumerate(ss_layout_bounds):
        node_idx = ss_node_index[i]
        node_id = ss_backend_node_ids[node_idx]
        if not bbox_dict.get(node_id) or not is_invalid_bound(bbox):
            bbox_dict[node_id] = bbox
    return bbox_dict


def create_text_node_dict(dom: DomSnapshotData, bbox_dict: dict[str, BoundingBox]) -> dict[int, TextNode]:
    """Create text mapping from backendNodeId to list of TextElements"""

    nodes, text_boxes = dom.nodes, dom.text_boxes

    def _get_text_value(text_boxes_idx: int, layout_idx: int) -> str:
        # Get text from layout which is actually rendered
        text_idx = dom.layout.get("text", [])[layout_idx]
        if text_idx == -1:
            return ""

        start = text_boxes.get("start", [])[text_boxes_idx]
        length = text_boxes.get("length", [])[text_boxes_idx]
        return dom.strings[text_idx][start : start + length].strip()

    def _get_text_bbox(text_boxes_idx: int, parent_id: int) -> BoundingBox:
        bbox = text_boxes.get("bounds", [])[text_boxes_idx]
        if not bbox or is_invalid_bound(bbox):
            return None

        parent_bbox = bbox_dict.get(parent_id)
        if not parent_bbox or is_invalid_bound(parent_bbox):
            return None

        # Ensure text bbox is within parent bbox (ellipsiss (...) case that text content will overflow)
        return bbox if bbox[2] <= parent_bbox[2] else parent_bbox

    text_node_dict: dict[int, TextNode] = {}
    for index, layout_idx in enumerate(text_boxes.get("layoutIndex", [])):
        node_idx = dom.layout.get("nodeIndex", [])[layout_idx]
        parent_idx = nodes.get("parentIndex", [])[node_idx]
        node_id = nodes.get("backendNodeId", [])[node_idx]
        parent_id = nodes.get("backendNodeId", [])[parent_idx]

        text = _get_text_value(index, layout_idx)
        if not text:
            continue  # Skip empty text

        bbox = _get_text_bbox(index, parent_id)
        if not bbox:
            continue  # Skip invalid bbox

        if node_id not in text_node_dict:
            text_node_dict[node_id] = TextNode(
                id=node_id,
                parent_id=parent_id,
                texts=[text],
                bboxes=[bbox],
            )
        else:
            text_node_dict[node_id].texts.append(text)
            text_node_dict[node_id].bboxes.append(bbox)

    return text_node_dict


def create_pseudo_set(dom: DomSnapshotData) -> set[str]:
    """Create a set of pseudo-class element backendNodeIds"""

    nodes = dom.nodes
    ss_backend_node_ids = nodes.get("backendNodeId", [])
    index_list = nodes.get("pseudoType", {})["index"]
    id_list = [ss_backend_node_ids[idx] for idx in index_list]
    return set(id_list)


def create_tree_node(dom: DomSnapshotData, node_id: int) -> TreeNode | None:
    """Create a TreeNode for the given backendNodeId"""
    nodes, strings = dom.nodes, dom.strings

    # Page nodes
    ss_backend_node_ids = nodes.get("backendNodeId", [])

    if node_id not in ss_backend_node_ids:
        return None

    idx = ss_backend_node_ids.index(node_id)
    tree_node = TreeNode(
        id=node_id,
        tag=strings[nodes["nodeName"][idx]],
        value=strings[nodes["nodeValue"][idx]],
        type=nodes["nodeType"][idx],
        depth=0,
    )

    return tree_node


def create_body_tree(dom: DomSnapshotData):
    """Analyze the DOM tree structure and return the body TreeNode"""
    nodes, strings = dom.nodes, dom.strings

    # Page nodes
    ss_backend_node_ids = nodes.get("backendNodeId", [])
    ss_parent_index = nodes.get("parentIndex", [])

    # Find the index of 'BODY' in strings
    body_str_idx = strings.index("BODY") if "BODY" in strings else -1
    body_tag_idx = nodes["nodeName"].index(body_str_idx) if body_str_idx != -1 else -1
    body_id = ss_backend_node_ids[body_tag_idx]
    body_node = create_tree_node(dom, body_id)

    tree_dict: dict[int, TreeNode] = {body_id: body_node}

    # Build parent mapping starting from nodes after BODY
    for idx in range(body_tag_idx + 1, len(ss_parent_index)):
        node_id = ss_backend_node_ids[idx]
        parent_idx = ss_parent_index[idx]
        parent_id = ss_backend_node_ids[parent_idx]

        tree_node = create_tree_node(dom, node_id)
        if not tree_node:
            continue  # Skip none node
        if tree_node.type == TEXT_NODE_TYPE and not tree_node.value.strip():
            continue  # Skip empty text node

        tree_dict[node_id] = tree_node  # Add to tree dict
        tree_dict[parent_id].children.append(tree_node)  # Append to parent's children

    return body_node


def update_tree_depths(node: TreeNode) -> int:
    """
    Update depth bottom-up:
    - leaf depth = 0
    - parent depth = max(child.depth) + 1
    """
    if not node.children:
        node.depth = 0
        return 0

    max_child_depth = 0
    for child in node.children:
        child_depth = update_tree_depths(child)
        max_child_depth = max(max_child_depth, child_depth)

    node.depth = max_child_depth + 1
    return node.depth


def concat_text_fragments(text_fragments: list[str]) -> str:
    """Concatenate text fragments with proper spacing rules."""

    no_space_after_chars = set("-([{（［｛<«“‘'\"")
    no_space_before_chars = set(")]}）］｝>»”’'\".,:;?!%。，、：；？！")

    def _is_cjk(ch: str) -> bool:
        if not ch:
            return False
        o = ord(ch)
        return (
            0x4E00 <= o <= 0x9FFF  # CJK Unified
            or 0x3400 <= o <= 0x4DBF  # CJK Ext A
            or 0x3040 <= o <= 0x30FF  # Hiragana/Katakana
            or 0x3000 <= o <= 0x303F  # CJK punctuation
            or 0xFF00 <= o <= 0xFFEF  # Fullwidth forms
        )

    result = ""
    for frag in text_fragments:
        if not result or not frag:
            result += frag
            continue

        prev_last_char = result[-1]
        cur_first_char = frag[0]

        # If either side explicitly forbids a space, or either side is CJK/fullwidth, skip adding a space
        if (
            prev_last_char in no_space_after_chars
            or cur_first_char in no_space_before_chars
            or _is_cjk(prev_last_char)
            or _is_cjk(cur_first_char)
        ):
            result += frag
            continue

        # Default: put a space between fragments
        result += " " + frag

    return result


def is_transparent_color(color_str: str) -> bool:
    """Check if the color string represents a fully transparent color"""
    if color_str.startswith("rgba(") and color_str.endswith(", 0)"):
        return True
    return False


def is_invalid_bound(b):
    """Check if the bound is valid (non-zero area)"""
    # Check for None or invalid format
    if not b or len(b) != 4 or b[2] == 0 or b[3] == 0:
        return True

    # Check for non-positive width/height
    if b[0] + b[2] <= 0 or b[1] + b[3] <= 0:
        return True

    return False


def is_overlay_bounds(top_bound: BoundingBox, bottom_bound: BoundingBox) -> bool:
    """Check if the top bounding box completely overlays the bottom bounding box"""

    x1, y1, w1, h1 = top_bound
    x2, y2, w2, h2 = bottom_bound

    if x1 <= x2 and x1 + w1 >= x2 + w2 and y1 <= y2 and y1 + h1 >= y2 + h2:
        return True

    return False


def is_intersect_bounds(bound1: BoundingBox, bound2: BoundingBox) -> bool:
    """Check if two bounding boxes intersect"""

    x1, y1, w1, h1 = bound1
    x2, y2, w2, h2 = bound2

    if x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2:
        return True

    return False


def compute_enclosing_bbox(bound_boxes: list[BoundingBox]) -> BoundingBox:
    """Compute the enclosing bounding box of multiple boxes [x, y, w, h]."""

    if not bound_boxes:
        return [0, 0, 0, 0]
    if len(bound_boxes) == 1:
        return bound_boxes[0]

    boxes = np.asarray(bound_boxes, dtype=float)
    x1 = boxes[:, 0].min()
    y1 = boxes[:, 1].min()
    x2 = (boxes[:, 0] + boxes[:, 2]).max()
    y2 = (boxes[:, 1] + boxes[:, 3]).max()
    return [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
