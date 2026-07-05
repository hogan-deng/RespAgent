"""DomSnapshot class to capture and process DOM snapshot data"""

from pathlib import Path

from common.browser import Browser
from metrics.utils.typings import (
    ELEM_NODE_TYPE,
    TEXT_NODE_TYPE,
    BoundingBox,
    PageElements,
    DomSnapshotData,
    NodeType,
    PriorConfig,
    TreeNode,
    TextNode,
    NodeElement,
    LayerElement,
    ModuleElement,
)
import metrics.utils.dom_utils as DomUtils


class SnapshotDocument:
    """Class to handle DOM snapshot document"""

    _MAX_MODULE_DEPTH = 6  # Maximum depth for module block consideration
    _MIN_MODULE_DEPTH = 2  # Minimum depth for module block consideration
    _MAX_MODULE_LENGTH = 10  # Maximum number of child nodes for a module block to avoid excessive merging
    _PLACEHOLDER_IMAGE_STYLE = {
        "background-color": "rgb(0, 0, 254)"
    }  # Replace image as a blue block to avoid diversity

    _TEXT_STYLES = [
        "color",
        "font-size",
        "font-weight",
        "font-style",
        "text-decoration",
    ]
    _BORDER_STYLE = [
        "border-color",
        "border-style",
        "border-width",
    ]
    _LAYER_STYLES = [
        "background-color",
        "background-image",
        "mask-image",
    ]
    _COMPUTED_STYLES = [
        "display",
        "float",
        "width",
        "height",
        "padding-top",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "border-top-width",
        "border-right-width",
        "border-bottom-width",
        "border-left-width",
        "text-indent",
        "text-shadow",
        "font-family",
        "letter-spacing",
        "opacity",
        "visibility",
        "overflow",
        "clip",
        "position",
        "z-index",
        *_TEXT_STYLES,
        *_BORDER_STYLE,
        *_LAYER_STYLES,
    ]
    _INLINE_STYLE_SET = {"inline", "inline-block", "ruby", "content"}

    def __init__(self, data: DomSnapshotData, style_dict: dict[int, dict[str, str]], prior_config: PriorConfig = None):
        """Initialize the SnapshotDocument by capturing DOM snapshot from the given URL and size"""

        self._dom = data
        self._style_dict = style_dict
        self._prior_config = prior_config or PriorConfig()
        self._attr_dict = DomUtils.create_attr_dict(self._dom)
        self._bbox_dict = DomUtils.create_bbox_dict(self._dom)

        self._text_node_dict = DomUtils.create_text_node_dict(self._dom, self._bbox_dict)

        self._pseudo_set = DomUtils.create_pseudo_set(self._dom)

    @classmethod
    async def create(
        cls, browser: Browser, url: str, resolution_str: str, prior_config: PriorConfig = None
    ) -> "SnapshotDocument":
        """Create SnapshotDocument instance by capturing DOM snapshot from the given URL and size"""
        resolution: tuple[int, int] = tuple(map(int, resolution_str.split("x")))
        snapshot_data = await DomUtils.retrieve_snapshot_data(browser, url, resolution, cls._COMPUTED_STYLES)
        style_dict = await DomUtils.retrieve_style_dict(browser, snapshot_data, cls._COMPUTED_STYLES)

        return cls(snapshot_data, style_dict, prior_config)

    def _get_text_node_by_id(self, node_id):
        """Get text element by backend node id"""
        return self._text_node_dict.get(node_id)

    def _get_style_value(self, node_id, property_name):
        """Get computed style by backend node id"""
        return self._style_dict.get(node_id, {}).get(property_name)

    def _get_text_style_by_id(self, node_id):
        """Get text-related computed styles by backend node id"""
        style = self._style_dict.get(node_id, {})
        text_style = {k: style.get(k) for k in self._TEXT_STYLES if style.get(k)}
        return text_style

    def _get_layer_style_by_id(self, node_id):
        """Get wrapping-related computed styles by backend node id"""

        # For elements with very small width or height, we consider them as non-layer nodes
        bbox = self.get_bbox_by_id(node_id)
        if bbox[2] <= 1 or bbox[3] <= 1:
            return {}

        style = self._style_dict.get(node_id, {})
        layer_style = {k: style.get(k) for k in self._LAYER_STYLES if style.get(k)}

        border_style = {k: style.get(k) for k in self._BORDER_STYLE if style.get(k)}
        border_sides = [k for k in ("top", "right", "bottom", "left") if style.get(f"border-{k}-width")]
        if len(border_sides) >= 2 and border_style.get("border-style") != "none":
            layer_style.update(border_style)

        # Assume white background if image exists but no color specified
        if not style.get("background-color") and style.get("background-image") == "url(rick.jpg)":
            layer_style |= self._PLACEHOLDER_IMAGE_STYLE

        return layer_style

    def _get_input_elment_label(self, node_id: int) -> str:
        """Get the placeholder text for an INPUT element by backend node id"""

        attrs = self._attr_dict.get(node_id, {})
        input_text = attrs.get("value") or attrs.get("placeholder") or ""
        return input_text

    def _get_select_element_label(self, children: list[TreeNode]) -> str:
        """Get the text of the selected option in a SELECT element"""
        default_text = ""
        for node in children:
            if node.tag == "OPTION":
                attrs = self._attr_dict.get(node.id, {})
                option_text = node.children[0].value.strip() if node.children else ""
                if "selected" in attrs:
                    return option_text
                if not default_text:
                    default_text = option_text
        return default_text

    def _generate_node_symbol(self, node: TreeNode) -> tuple[NodeType, str]:
        """Create a mock TextNode for non-text elements"""
        symbol_type = None
        symbol_style = None
        symbol_label = ""
        if node.tag == "svg" and node.children:
            symbol_type = NodeType.MEDIA
            img_url = self._attr_dict.get(node.children[0].id, {}).get("href", "")
            img_name = Path(img_url).stem
            symbol_style = {"content": img_name, "color": self._get_style_value(node.id, "color")}
        elif img_url := self._get_style_value(node.id, "mask-image"):
            symbol_type = NodeType.MEDIA
            img_url = img_url.strip("url()") if img_url.startswith("url(") else img_url
            img_name = Path(img_url).stem
            symbol_style = {"content": img_name, "background-color": self._get_style_value(node.id, "background-color")}
        elif node.tag == "IMG" or (bg_image := self._get_style_value(node.id, "background-image")):
            symbol_type = NodeType.MEDIA
            img_url = (
                self._attr_dict.get(node.id, {}).get("src", "")
                if node.tag == "IMG"
                else (bg_image.strip("url()") if bg_image.startswith("url(") else bg_image)
            )

            img_name = Path(img_url).stem
            symbol_style = (
                self._PLACEHOLDER_IMAGE_STYLE
                if img_name == "rick"
                else {"content": img_name, "background-color": "rgb(0, 0, 0)"}
            )
        elif bg_color := self._get_style_value(node.id, "background-color"):
            symbol_type = NodeType.MEDIA
            symbol_style = {"content": "", "background-color": bg_color}
        elif node.tag in {"INPUT", "TEXTAREA", "SELECT"}:
            if node.tag in {"INPUT", "TEXTAREA"}:
                symbol_label = self._get_input_elment_label(node.id)
            elif node.tag == "SELECT":
                symbol_label = self._get_select_element_label(node.children)
            symbol_type = NodeType.FIELD
            symbol_style = {"color": self._get_style_value(node.id, "color")}

        return symbol_type, symbol_style, symbol_label

    def _is_hidden_node(self, node_id, parent_background) -> bool:
        """Check if the element is hidden based on its and its ancestors' styles"""
        style = self._style_dict.get(node_id)

        # If no style info, consider it hidden (Only display none elements have no style info)
        if not style:
            return True

        def _is_indent_hidden(text_indent: str | None, overflow: str) -> bool:
            if not text_indent or overflow != "hidden":
                return False

            try:
                if text_indent.endswith("%"):
                    indent_value = int(text_indent[:-1])
                    return indent_value >= 100
                if text_indent.endswith("px"):
                    indent_value = int(text_indent[:-2])
                    return indent_value > 0
            except ValueError:
                pass

            return False

        # Check for various hidden styles
        # Consider visibility:hidden as hidden even though children can overwrite it (rarely)
        is_hidden = style.get("visibility") == "hidden" or style.get("clip") in {
            "rect(0px, 0px, 0px, 0px)",
            "rect(1px, 1px, 1px, 1px)",
        }

        if not is_hidden and self._text_node_dict.get(node_id):
            # Check for text node specific hidden styles
            is_hidden = (
                style.get("color") is None
                or _is_indent_hidden(style.get("text-indent"), style.get("overflow"))
                or (style.get("color") == parent_background and style.get("text-shadow") is None)
            )
        return bool(is_hidden)

    def _is_inherit_hidden(self, node_id) -> bool:
        """Check if any ancestor element is hidden based on styles"""
        style = self._style_dict.get(node_id)

        # If no style info, consider it hidden (Only display none elements have no style info)
        if not style:
            return True

        # Check for various hidden styles
        zero_size_x = all(k not in style for k in ("padding-left", "padding-right", "width"))
        zero_size_y = all(k not in style for k in ("padding-top", "padding-bottom", "height"))
        micro_size = style.get("width") == "1px" and style.get("height") == "1px"
        overflow_hidden = style.get("overflow") != "visible" and (zero_size_x or zero_size_y or micro_size)

        is_hidden = style.get("opacity") == "0" or overflow_hidden
        return bool(is_hidden)

    def _is_valid_module_size(self, node_bbox: BoundingBox) -> bool:
        """Check if the node size is within the valid range for module block consideration"""
        return node_bbox[3] < self._dom.resolution[1] / 4

    def _is_valid_module_children(self, node: TreeNode, max_length: int) -> bool:
        """Check if the node length is within the valid range for max length consideration"""
        if len(node.children) > max_length or self.get_meta_id(node.id) in self._prior_config.layer_ids:
            return False
        for child in node.children:
            if not self._is_valid_module_children(child, max_length):
                return False
        return True

    def _is_valid_module_depth(self, node: TreeNode) -> bool:
        """Check if the node depth is within the valid range for module block consideration"""
        valid_depth = self._MIN_MODULE_DEPTH <= node.depth <= self._MAX_MODULE_DEPTH
        return valid_depth and self._is_valid_module_children(node, self._MAX_MODULE_LENGTH)

    def is_collecting_module(self, node: TreeNode, is_layer_node: bool) -> bool:
        """Determine whether the current node should be considered as a module block for collecting its descendant text nodes"""

        node_display = self._get_style_value(node.id, "display")
        if node.type != ELEM_NODE_TYPE or node.id in self._pseudo_set or node_display in self._INLINE_STYLE_SET:
            return False

        is_module_node = (
            is_layer_node
            or node.tag in ["UL", "OL", "TABLE"]
            or node_display in {"block", "grid", "flex", "table"}
            or self._get_style_value(node.id, "position") in {"absolute", "fixed"}
        )
        if not is_module_node:
            return False

        node_bbox = self.get_bbox_by_id(node.id)
        if not node_bbox or DomUtils.is_invalid_bound(node_bbox):
            return False

        return self._is_valid_module_size(node_bbox) or self._is_valid_module_depth(node)

    def _collect_nodes_recursive(
        self,
        elem_store: PageElements,
        node: TreeNode,
        parent_node: TreeNode,
        is_recursive_collecting: bool = False,
    ):
        """Recursively extract elements from the DOM tree node"""

        # Use list to collect text node or layer meta id from children
        collected_nodes: list[tuple[TreeNode, TextNode | NodeElement]] = []

        # Collect texts from the current node
        meta_id = self.get_meta_id(node.id, parent_node.id)

        # If the current node is in the exclude list, skip collecting nodes in this branch
        if meta_id in self._prior_config.exclude_nodes:
            return collected_nodes

        # Determine if current node is a module block for collecting descendant nodes
        is_layer_node = meta_id in self._prior_config.layer_ids
        is_prior_module = meta_id in self._prior_config.include_modules
        is_node_collecting = is_prior_module or self.is_collecting_module(node, is_layer_node)

        # Recursively process child nodes
        if node.children and node.tag != "svg":
            # Recursively collect texts from child nodes
            for child in node.children:
                is_child_collecting = is_node_collecting or is_recursive_collecting
                child_collect_result = self._collect_nodes_recursive(elem_store, child, node, is_child_collecting)
                if child_collect_result is True:
                    # If child node is a collecting module, consume the collected nodes as soon as possible
                    if collected_nodes:
                        self._consume_collected_nodes(elem_store, collected_nodes)
                        collected_nodes.clear()
                elif isinstance(child_collect_result, list):
                    # If child node is not a collecting module, continue to collect nodes and append the results
                    collected_nodes.extend(child_collect_result)
        else:
            node_elem = self._create_node_element(node)
            if isinstance(node_elem, TextNode):
                collected_nodes.append((parent_node, node_elem))
            elif isinstance(node_elem, NodeElement):
                collected_nodes.append((node, node_elem))

        # Create block element if current node is a container
        if (is_prior_module or not is_recursive_collecting) and is_node_collecting and collected_nodes:
            layer_bbox = self.get_bbox_by_id(node.id) if is_prior_module or is_layer_node else None
            module_elem = self._create_module_element(elem_store, collected_nodes, layer_bbox)
            self._add_module_element(elem_store, module_elem, meta_id)
            return True  # Return True to indicate collecting is done in this branch

        return collected_nodes  # Return collected nodes for parent module element creation

    def _consume_collected_nodes(
        self, elem_store: PageElements, collected_nodes: list[tuple[TreeNode, TextNode | NodeElement | LayerElement]]
    ):
        """Group collected nodes by their nearest collecting ancestor and create module elements for each group."""
        # Accumulates nodes until a collecting module boundary is found
        pending_nodes: list[tuple[TreeNode, TextNode | NodeElement | LayerElement]] = []
        # Maps module meta-id -> list of (node, element) pairs belonging to that module
        module_node_groups: dict[str, list[tuple[TreeNode, TextNode | NodeElement | LayerElement]]] = {}

        for node, elem in collected_nodes:
            # Ignore layer elements in this consume function since it is anomaly processed
            if isinstance(elem, LayerElement):
                continue

            meta_id = self.get_meta_id(node.id)
            if meta_id in module_node_groups:
                module_node_groups[meta_id].append((node, elem))
                continue

            is_layer_node = meta_id in self._prior_config.layer_ids
            is_collecting = self.is_collecting_module(node, is_layer_node)

            pending_nodes.append((node, elem))
            if is_collecting:
                # Flush pending nodes into this module's group
                module_node_groups[meta_id] = pending_nodes
                pending_nodes = []

        if module_node_groups:
            # Append any remaining pending nodes to the last module group
            if pending_nodes:
                last_meta_id = next(reversed(module_node_groups))
                module_node_groups[last_meta_id].extend(pending_nodes)

            for meta_id, module_nodes in module_node_groups.items():
                layer_bbox = elem_store.layers[meta_id].bbox if meta_id in elem_store.layers else None
                module_elem = self._create_module_element(elem_store, module_nodes, layer_bbox)
                self._add_module_element(elem_store, module_elem, meta_id)
        else:
            # No collecting module boundary found — wrap all collected nodes into one module element
            first_node = pending_nodes[0][0]
            meta_id = self.get_meta_id(first_node.id)
            module_elem = self._create_module_element(elem_store, collected_nodes, None)
            self._add_module_element(elem_store, module_elem, meta_id)

    def _create_node_element(self, node: TreeNode) -> TextNode | None:
        """
        Collect elements from the given DOM tree node
        Return:
            - TextNode if a text element is created
            - None if no text element found
        """

        # Process text nodes
        if node.type == TEXT_NODE_TYPE:
            return self._get_text_node_by_id(node.id)

        # Skip non-element nodes
        if node.type != ELEM_NODE_TYPE:
            return None

        # Skip specific non-content elements
        if node.tag in {"HR"}:
            return None

        # Process atom elements (INPUT, IMG, etc.) without children
        symbol_type, symbol_style, symbol_text = self._generate_node_symbol(node)
        if symbol_type and symbol_style:
            node_bbox = self.get_bbox_by_id(node.id)
            if not DomUtils.is_invalid_bound(node_bbox):
                return NodeElement(
                    type=symbol_type,
                    text=symbol_text,
                    bboxes=[node_bbox],
                    style=symbol_style,
                    children=[],
                )

        # Process pseudo text nodes
        if node.id in self._pseudo_set:
            return self._get_text_node_by_id(node.id)

        return None

    def _create_module_element(
        self,
        elem_store: PageElements,
        collected_nodes: list[tuple[TreeNode, TextNode | NodeElement]],
        layer_bbox: BoundingBox | None = None,
    ):
        """Create a BlockElement from the collected text elements, merging similar styled texts"""

        text_nodes: list[TextNode] = []

        text_meta_ids: list[str] = []
        symbol_meta_ids: list[str] = []

        module_texts: list[str] = []
        module_bboxes: list[BoundingBox] = []

        for node, item in collected_nodes:
            if isinstance(item, TextNode):
                # Collect text nodes for merging
                module_texts.extend(item.texts)
                module_bboxes.extend(item.bboxes)
                text_nodes.append(item)
            elif isinstance(item, NodeElement):
                # Collect symbol nodes directly
                module_bboxes.extend(item.bboxes)
                item_meta_id = self.get_meta_id(node.id)
                symbol_meta_ids.append(item_meta_id)
                elem_store.nodes[item_meta_id] = item

        # Concatenate all texts
        text_label = DomUtils.concat_text_fragments(module_texts)

        # Compute enclosing bounding box
        bbox_value = layer_bbox if layer_bbox else DomUtils.compute_enclosing_bbox(module_bboxes)

        # Merge text nodes by style
        text_meta_ids = self._merge_text_nodes_by_style(elem_store, text_nodes)

        return ModuleElement(
            text=text_label,
            bbox=bbox_value,
            leaf_texts=text_meta_ids,
            leaf_signs=symbol_meta_ids,
        )

    def _add_module_element(
        self,
        elem_store: PageElements,
        module_elem: ModuleElement,
        meta_id: str,
    ):
        """Add the created module element to the element store and update the meta id mapping"""

        if meta_id in elem_store.modules:
            # If there is already a module element for this meta id, we need to merge them
            existing_module = elem_store.modules[meta_id]

            # Merge text
            existing_module.text = DomUtils.concat_text_fragments([existing_module.text, module_elem.text])

            # Merge bounding box
            existing_module.bbox = DomUtils.compute_enclosing_bbox([existing_module.bbox, module_elem.bbox])

            # Merge leaf nodes and signs
            existing_module.leaf_texts = list(set(existing_module.leaf_texts + module_elem.leaf_texts))
            existing_module.leaf_signs = list(set(existing_module.leaf_signs + module_elem.leaf_signs))
        else:
            elem_store.modules[meta_id] = module_elem

    def _merge_text_nodes_by_style(self, elem_store: PageElements, text_nodes: list[TextNode]) -> list[str]:
        """Merge text nodes with similar styles into node elements, return list of children meta-ids"""
        children_meta_ids: list[str] = []
        style_groups: dict[tuple[tuple[str, str]], str] = {}

        for node in text_nodes:
            # Skip if not acctually a text node (may be collected as symbol node)
            if not self._get_text_node_by_id(node.id):
                continue

            meta_id = self.get_meta_id(node.parent_id)

            node_style = self._get_text_style_by_id(node.id)
            style_key = tuple(sorted(node_style.items()))
            leader_id = style_groups.get(style_key)

            if not leader_id:
                # Create text node elemenet
                if meta_id not in elem_store.nodes:
                    elem_store.nodes[meta_id] = NodeElement(
                        type=NodeType.TEXT,
                        text=DomUtils.concat_text_fragments(node.texts),
                        bboxes=node.bboxes,
                        style=node_style,
                        children=[],
                    )
                else:
                    # There are two text nodes with the same meta ID when a node contains both pseudo-content and text children.
                    prev_node = elem_store.nodes[meta_id]
                    prev_node.text = DomUtils.concat_text_fragments([prev_node.text] + node.texts)
                    prev_node.bboxes.extend(node.bboxes)
                    prev_node.style = node_style

                style_groups[style_key] = meta_id
                children_meta_ids.append(meta_id)
                continue

            leader = elem_store.nodes[leader_id]
            leader.text = DomUtils.concat_text_fragments([leader.text] + node.texts)
            leader.bboxes.extend(node.bboxes)
            leader.children.append(meta_id)

            # Remove merged sign node which added in the create module element method
            if not node.texts and meta_id in elem_store.nodes:
                del elem_store.nodes[meta_id]

        return children_meta_ids

    def _pre_remove_overlapped_children(self, root_node: TreeNode) -> None:
        """Filter out child nodes that are completely overlapped by other child nodes"""

        if not root_node.children:
            return

        def _z_index(child: TreeNode) -> int | None:
            z_raw = self._get_style_value(child.id, "z-index")
            if not z_raw or z_raw == "auto":
                return None
            try:
                return int(z_raw)
            except ValueError:
                return None

        def _is_cover_candidate(child: TreeNode) -> bool:
            if child.type != ELEM_NODE_TYPE:
                return False
            if self._get_style_value(child.id, "position") == "static":
                return False
            bg_image = self._get_style_value(child.id, "background-image")
            bg_color = self._get_style_value(child.id, "background-color")
            if not bg_image and (not bg_color or DomUtils.is_transparent_color(bg_color)):
                return False

            z_index = _z_index(child)
            return z_index is not None and z_index > 0

        def _filter_overlapped_nodes(child_nodes: list[TreeNode]) -> None:
            # Sort candidates by z-index descending
            candidates = list(enumerate(c for c in child_nodes if _is_cover_candidate(c)))
            candidates.sort(key=lambda i: (_z_index(i[1]) or 0, i[0]), reverse=True)

            # Fast membership checks
            processed_ids: set[str] = set()

            for _, top in candidates:
                # Skip if this candidate was removed
                if top.id in processed_ids:
                    continue

                # Mark this candidate as processed
                processed_ids.add(top.id)

                # Skip if invalid bounding box
                top_bbox = self.get_bbox_by_id(top.id)
                if not top_bbox or DomUtils.is_invalid_bound(top_bbox):
                    continue

                # Remove children fully covered by this top candidate
                for i in range(len(child_nodes) - 1, -1, -1):
                    child = child_nodes[i]
                    if child.id in processed_ids:
                        continue
                    child_bbox = self.get_bbox_by_id(child.id)
                    if child_bbox and DomUtils.is_overlay_bounds(top_bbox, child_bbox):
                        processed_ids.add(child.id)
                        del child_nodes[i]

            for child in child_nodes:
                if child.children:
                    _filter_overlapped_nodes(child.children)

        _filter_overlapped_nodes(root_node.children)

    def _pre_remove_invisible_nodes(self, root_node: TreeNode) -> None:
        """Filter out text nodes that are invisible due to content or styles"""

        if not root_node.children:
            return None

        def _filter_invisible_nodes(children: list[TreeNode], parent_background: str) -> list[TreeNode]:
            new_children: list[TreeNode] = []
            for node in children:
                node_bbox = self.get_bbox_by_id(node.id)
                # Skip nodes without bounding box (considered invisible)
                if not node_bbox:
                    continue

                # Skip nodes with no size and no children (considered invisible)
                if not node.children and DomUtils.is_invalid_bound(node_bbox):
                    continue

                # Skip if bounding box is out of viewport (considered invisible)
                if node_bbox[2] and node_bbox[3]:
                    if node_bbox[0] + node_bbox[2] <= 0 or node_bbox[0] >= self._dom.body_bbox[2]:
                        continue

                # Skip text nodes without text content
                if node.type == TEXT_NODE_TYPE and not self._get_text_node_by_id(node.id):
                    continue

                # Skip if node is hidden by its own styles or inherited hidden styles from ancestors
                if self._is_inherit_hidden(node.id) or self._is_hidden_node(node.id, parent_background):
                    continue

                # Update background color if specified in styles
                node_background = self._get_style_value(node.id, "background-color") or parent_background
                if self._get_style_value(node.id, "background-image") and node_background:
                    node_background = None  # Background image exists, ignore background color:

                # Recurse
                if node.children:
                    node.children = _filter_invisible_nodes(node.children, node_background)

                new_children.append(node)
            return new_children

        root_background = self._get_style_value(root_node.id, "background-color")
        root_node.children = _filter_invisible_nodes(root_node.children, root_background)
        return None

    def _collect_layers_hierarchy(self, elem_store: PageElements, body_tree: TreeNode) -> None:
        """Collect a hierarchical LayerElement tree from the DOM root, attach background layers, then prune overlaps."""

        def _attach_descendant_layers(node: TreeNode, current_layer: LayerElement):
            for child in node.children:
                # Skip leaf nodes
                if not child.children:
                    continue

                layer_style = self._get_layer_style_by_id(child.id)
                layer_bbox = self.get_bbox_by_id(child.id)
                if layer_style and not DomUtils.is_invalid_bound(layer_bbox):
                    child_meta_id = self.get_meta_id(child.id)
                    current_layer.children.append(child_meta_id)
                    elem_store.layers[child_meta_id] = LayerElement(
                        bbox=layer_bbox,
                        style=layer_style,
                        children=[],
                    )
                    # If the layer fully covers the body, remove the root layer to avoid redundancy
                    _attach_descendant_layers(child, elem_store.layers[child_meta_id])
                    if (
                        root_meta_id in elem_store.layers
                        and layer_bbox[2] == self._dom.body_bbox[2]
                        and layer_bbox[3] == self._dom.body_bbox[3]
                    ):
                        del elem_store.layers[root_meta_id]
                else:
                    _attach_descendant_layers(child, current_layer)

        # Create root layer element
        root_meta_id = self.get_meta_id(body_tree.id)
        root_base_style = {"background-color": "rgb(255, 255, 255)"} | self._get_layer_style_by_id(body_tree.id)
        elem_store.layers[root_meta_id] = LayerElement(
            bbox=self._dom.body_bbox,
            style=root_base_style,
            children=[],
        )

        # Attach descendant layers recursively
        _attach_descendant_layers(body_tree, elem_store.layers[root_meta_id])

        # Remove overlapped layers starting from root
        self._post_remove_overlapped_layers(elem_store.layers)

    def _post_remove_overlapped_layers(self, layer_dict: dict[str, LayerElement]) -> None:
        """Filter out layer elements that are completely overlapped by their descendants.
        If a child's bbox (or the union of its subtree bboxes) fully overlays the parent's bbox,
        delete the parent layer and promote its children into the parent's parent.
        """

        def _postorder_prune_and_union(parent_id: str, layer_id: str) -> tuple[int, int, int, int]:
            """Post-order DFS.
            Returns the union bbox of the current subtree. May delete the current layer if overlaid.
            """
            layer = layer_dict.get(layer_id)
            cur_bbox = layer.bbox

            # 1) Process children first and collect their subtree union bboxes
            child_union_bboxes: list[tuple[int, int, int, int]] = []
            for cid in list(layer.children):
                union_bbox = _postorder_prune_and_union(layer_id, cid)
                child_union_bboxes.append(union_bbox)

            # 2) If current layer is fully overlapped, delete current layer and promote its children into the parent
            children_union_bbox = DomUtils.compute_enclosing_bbox(child_union_bboxes) if child_union_bboxes else None
            if children_union_bbox and DomUtils.is_overlay_bounds(children_union_bbox, cur_bbox):
                new_children = []
                parent = layer_dict.get(parent_id)
                for x in parent.children:
                    if x == layer_id:
                        new_children.extend(layer.children)  # promote grandchildren
                    else:
                        new_children.append(x)
                parent.children = new_children
                # Remove the current layer from the dictionary
                del layer_dict[layer_id]
                # Return the union of children (the subtree remains, just one level higher)
                return children_union_bbox

            # 3) Otherwise, keep current layer; return union of current + children
            if children_union_bbox:
                return DomUtils.compute_enclosing_bbox([cur_bbox, children_union_bbox])

            # 4) No children, return current bbox
            return cur_bbox

        def _flatten_same_style_layers(layer: LayerElement, children: list[str]) -> list[str]:
            """Flatten nested layers that have identical style to their parent.
            If a child has the same style, replace it with its own children and remove it.
            Preserves child order and recurses depth-first.
            """
            new_children: list[str] = []
            for cid in children:
                child_layer = layer_dict.get(cid)
                # Compare styles defensively
                if child_layer.style == layer.style:
                    # Replace child with its (flattened) children
                    flattened = _flatten_same_style_layers(layer, child_layer.children)
                    new_children.extend(flattened)
                    # Remove the redundant child layer node
                    del layer_dict[cid]
                else:
                    # Recurse into child first, then keep the child id in order
                    child_layer.children = _flatten_same_style_layers(child_layer, child_layer.children)
                    new_children.append(cid)
            return new_children

        # Prune overlaps bottom-up
        parent_layer_id = list(layer_dict)[0]
        parent_layer = layer_dict.get(parent_layer_id)
        for cid in list(parent_layer.children):
            _postorder_prune_and_union(parent_layer_id, cid)

        # Merge redundant backgrounds
        parent_layer.children = _flatten_same_style_layers(parent_layer, parent_layer.children)

    def _post_merge_module_elements(self, elem_store: PageElements):
        """Merge module elements based on the merge configuration in prior config"""

        for merge_list in self._prior_config.merge_modules:
            if not merge_list:
                continue

            base_meta_id = merge_list[0]
            if base_meta_id not in elem_store.modules:
                continue

            for meta_id in merge_list[1:]:
                if meta_id not in elem_store.modules:
                    continue
                base_module = elem_store.modules[base_meta_id]
                merging_module = elem_store.modules[meta_id]

                # Merge text
                base_module.text = DomUtils.concat_text_fragments([base_module.text, merging_module.text])

                # Merge bounding box
                base_module.bbox = DomUtils.compute_enclosing_bbox([base_module.bbox, merging_module.bbox])

                # Merge leaf nodes and signs
                base_module.leaf_texts = list(set(base_module.leaf_texts + merging_module.leaf_texts))
                base_module.leaf_signs = list(set(base_module.leaf_signs + merging_module.leaf_signs))

                # Remove the merged module element
                del elem_store.modules[meta_id]

    def get_meta_id(self, node_id, parent_id=None):
        """Get meta-id value by backend node id, return node id if no meta-id found"""
        meta_id = self._attr_dict.get(node_id, {}).get("data-meta-id")

        # If no meta-id is set on the node, try to get it from the parent
        if not meta_id and parent_id:
            parent_meta_id = self._attr_dict.get(parent_id, {}).get("data-meta-id")
            if parent_meta_id:
                return f"{parent_meta_id}c"

        return meta_id if meta_id else f"NODE_{node_id}"

    def get_bbox_by_id(self, node_id):
        """Get bounding box by backend node id"""
        return self._bbox_dict.get(node_id)

    def export_element_data(self) -> PageElements:
        """Export extracted DOM elements data"""

        # Create element store and extract elements starting from body
        elem_store = PageElements()
        body_tree = DomUtils.create_body_tree(self._dom)

        # Clean up invisible text nodes
        self._pre_remove_invisible_nodes(body_tree)

        # Clean up overlapped child nodes (after invisible text removal)
        self._pre_remove_overlapped_children(body_tree)

        # Update tree depths
        DomUtils.update_tree_depths(body_tree)

        # Collect layer hierarchy
        self._collect_layers_hierarchy(elem_store, body_tree)
        self._prior_config.layer_ids = set(elem_store.layers.keys())

        # Collect module and node elements (excluding body root)
        for child in body_tree.children:
            child_collect_result = self._collect_nodes_recursive(elem_store, child, body_tree)
            if isinstance(child_collect_result, list) and child_collect_result:
                self._consume_collected_nodes(elem_store, child_collect_result)

        # Merge module elements based on prior configuration
        self._post_merge_module_elements(elem_store)

        # Remove layer information that current evluation does not utilize to avoid confusion
        elem_store.layers = {}

        return elem_store
