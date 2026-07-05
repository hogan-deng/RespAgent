"""Module for generating metadata JSON files for web page snapshots."""

import json
from pathlib import Path

from common.browser import Browser
from common.logger import common_logger
from common.json_output import json_serializable
from common.config import PageConfig
from metrics.dom_snapshot import PageElements, SnapshotDocument


async def generate_metadata(browser: Browser, config: PageConfig, overwrite: bool = False) -> dict[str, PageElements]:
    """Generate and save the metadata JSON file using an existing Browser instance."""

    # Validate viewport configuration
    resolutions: list[str] = list(config.screenshots)
    if not resolutions:
        common_logger.error("No viewport configured; raising error for %s", config.name)
        raise ValueError("No viewport configured in PageConfig.screenshots")

    metadata_path = Path(config.metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    # If existing and not overwriting, read and return
    if metadata_path.exists() and not overwrite:
        return load_metadata_from_json(metadata_path)

    # Generate metadata for each viewport
    metadata: dict[str, PageElements] = {}
    for size in resolutions:
        # Capture snapshot and extract elements
        snapshot_document = await SnapshotDocument.create(browser, config.url, size)
        metadata[size] = snapshot_document.export_element_data()

        # Update pre_modules for the next iteration
        # prior_config.group_ids = set(metadata[size].modules.keys())
    # Atomic write to avoid partial files
    _write_export_metadata(metadata_path, metadata)

    return metadata


def load_metadata_from_json(path: Path) -> dict[str, PageElements]:
    """Read an existing metadata JSON file into DomElements."""
    with open(path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    return {k: PageElements.from_json(v) for k, v in json_data.items()}


def _write_export_metadata(path: Path, data: dict[str, PageElements]) -> None:
    """Write metadata to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=json_serializable, indent=2)
