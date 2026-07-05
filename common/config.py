"""Typing schemas for common module"""

import json
from dataclasses import dataclass
from pathlib import Path

import os
from dotenv import load_dotenv

load_dotenv()
WEB_SERVER_PORT = int(os.getenv("PORT", "8000"))

RESOLUTION_LIST = [
    (1920, 1080),
    (1280, 720),
    (1024, 768),
    (768, 1024),
    (412, 915),
    (360, 800),
]
"""Resolution options for screenshots"""


@dataclass
class PageConfig:
    """Data structure for storing item information."""

    name: str
    url: str
    root: str
    metadata: str
    prototypes: dict[str, str]
    screenshots: dict[str, str]

    def get_html_path(self) -> Path:
        """Get the local file path for the HTML file based on the URL."""
        return Path(self.url.replace(f"http://localhost:{WEB_SERVER_PORT}/", "results/"))

    def get_feedback_path(self) -> Path:
        """Get the local file path for the feedback JSON file based on the metadata path."""
        return Path(self.metadata.replace("metadata/", "feedbacks/"))

    def get_diff_path(self) -> Path:
        """Get the local file path for the diff JSON file based on the metadata path."""
        return Path(self.metadata.replace("metadata/", "diffs/"))


def get_html_name_list(file_name: str | None = None, dataset="html") -> list[str]:
    """Retrieve all file names from the configuration file, or return a specific file if provided."""
    if file_name:
        return [file_name]

    with open("datasets/config.json", "r", encoding="utf-8") as f:
        config_data = json.load(f)
    return config_data[dataset]


def get_html_prototypes(page_name: str) -> dict[str, str]:
    """Get the prototype images for a given file name."""
    page_stem = Path(page_name).stem
    return {
        f"{size[0]}x{size[1]}": f"datasets/screenshots/{size[0]}x{size[1]}/{page_stem}.png" for size in RESOLUTION_LIST
    }


def get_page_config(
    root_path: str,
    page_name: str,
    iteration: int,
) -> PageConfig:
    """Generate the file path for a given filename and group."""

    page_stem = Path(page_name).stem
    iter_path = f"{root_path}/iter_{iteration:02X}"
    iter_url = iter_path.replace("results/", "")  # Map results path to URL path
    return PageConfig(
        root=root_path,
        name=page_stem,
        url=f"http://localhost:{WEB_SERVER_PORT}/{iter_url}/{page_stem}.html",
        metadata=f"{iter_path}/metadata/{page_stem}.json",
        prototypes=get_html_prototypes(page_name),
        screenshots={
            f"{size[0]}x{size[1]}": f"{iter_path}/screenshots/{size[0]}x{size[1]}/{page_stem}.png"
            for size in RESOLUTION_LIST
        },
    )
