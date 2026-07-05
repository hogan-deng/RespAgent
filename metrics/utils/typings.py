"""Dataclasses for DOM typing and block node representation"""

from enum import Enum
from dataclasses import dataclass, field


ELEM_NODE_TYPE = 1
"""Node type constant for element nodes"""
TEXT_NODE_TYPE = 3
"""Node type constant for text nodes"""


class NodeType(str, Enum):
    """Node types in DOM snapshot"""

    LAYER = "layer"
    """element with background or border"""
    TEXT = "text"
    """text element"""
    MEDIA = "media"
    """image, video, svg, canvas"""
    FIELD = "field"
    """input, textarea, select"""


BoundingBox = tuple[int, int, int, int]
"""Type alias for bounding box: (x, y, width, height)"""


@dataclass
class PriorConfig:
    """Data structure for storing prior configuration for snapshot generation."""

    include_modules: set[str] = field(default_factory=set)
    exclude_nodes: set[str] = field(default_factory=set)
    merge_modules: list[list[str]] = field(default_factory=list)


@dataclass
class DomSnapshotData:
    """Dataclass for snapshot data"""

    nodes: dict
    layout: dict
    text_boxes: dict
    strings: list[str]

    resolution: tuple[int, int]
    body_bbox: BoundingBox


@dataclass(slots=True)
class TreeNode:
    """Dataclass for tree node representation"""

    id: int
    tag: str
    value: str
    depth: int
    type: int  # ELEMENT_NODE or TEXT_NODE
    children: list["TreeNode"] = field(default_factory=list)


@dataclass(slots=True)
class TextNode:
    """Dataclass for text element in the DOM snapshot"""

    id: int
    parent_id: int
    texts: list[str]
    bboxes: list[BoundingBox]


@dataclass(slots=True)
class NodeElement:
    """Dataclass for node element in the metadata"""

    type: NodeType
    text: str
    bboxes: list[BoundingBox]
    style: dict[str, str]
    children: list[str]


@dataclass(slots=True)
class LayerElement:
    """Dataclass for layer element in the metadata"""

    bbox: BoundingBox
    style: dict[str, str]
    children: list[str]


@dataclass(slots=True)
class ModuleElement:
    """Dataclass for module element in the metadata"""

    text: str
    bbox: BoundingBox
    leaf_texts: list[str]
    leaf_signs: list[str]


@dataclass(slots=True)
class PageElements:
    """Dataclass for all DOM elements extracted from snapshot"""

    nodes: dict[str, NodeElement] = field(default_factory=dict)
    layers: dict[str, LayerElement] = field(default_factory=dict)
    modules: dict[str, ModuleElement] = field(default_factory=dict)

    @staticmethod
    def from_json(data: dict) -> "PageElements":
        """Create DomElements from JSON string"""

        nodes = {k: NodeElement(**v) for k, v in data.get("nodes", {}).items()}
        layers = {k: LayerElement(**v) for k, v in data.get("layers", {}).items()}
        modules = {k: ModuleElement(**v) for k, v in data.get("modules", {}).items()}
        return PageElements(nodes=nodes, layers=layers, modules=modules)


@dataclass(slots=True)
class ComparisonResults:
    """Dataclass for all comparison elements extracted from evaluation"""

    module_stats: dict[str, int | float]
    node_stats: dict[str, int | float]

    module_ids: list[tuple[str, str]]
    node_ids: list[tuple[str, str]]

    source_elements: PageElements
    generated_elements: PageElements

    @staticmethod
    def from_json(data: dict) -> "ComparisonResults":
        """Create ComparisonResults from JSON string"""

        module_stats = data.get("module_stats", {})
        node_stats = data.get("node_stats", {})
        module_ids = [tuple(item) for item in data.get("module_ids", [])]
        node_ids = [tuple(item) for item in data.get("node_ids", [])]
        source_elements = PageElements.from_json(data.get("source_elements", {}))
        generated_elements = PageElements.from_json(data.get("generated_elements", {}))
        return ComparisonResults(
            module_stats=module_stats,
            node_stats=node_stats,
            module_ids=module_ids,
            node_ids=node_ids,
            source_elements=source_elements,
            generated_elements=generated_elements,
        )
