"""Dataset management script for generating metadata and screenshots, and for zipping/unzipping dataset files."""

import os
import re
import json
import math
import asyncio
import argparse
import zipfile
from pathlib import Path


import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv

from common.config import PageConfig, get_html_prototypes
from common.browser import launch_browser
from common.metadata import generate_metadata
from common.screenshots import capture_screenshots_with_browser


load_dotenv()
WEB_SERVER_PORT = int(os.getenv("PORT", "8000"))


def _file_name_sort_key_simple(file_name: str) -> int:
    """Sort files based on the numeric part of their names."""
    parts = re.findall(r"([^\d]*)(\d+)", file_name)
    if parts:
        return [int(part) if part.isdigit() else part for part in parts[0]]
    return [file_name]


def _select_sample_files(file_names: list[str], bin_size=50, bin_samples=3) -> list[str]:
    """
    Select representative sample files using stratified percentile sampling.

    Args:
        file_names: List of file names sorted by page complexity.
        bin_size: Number of files per bin.
        bin_samples: Number of samples selected from each bin.

    Returns:
        List of selected sample file names.
    """
    selected = []
    for start in range(0, len(file_names), bin_size):
        bin_files = file_names[start : start + bin_size]
        f_size = len(bin_files)
        if f_size == 0:
            continue

        # evenly spaced percentile positions (e.g., 25%, 50%, 75%)
        s_size = min(bin_samples, f_size)
        percentiles = [(i + 1) / (s_size + 1) for i in range(s_size)]
        for p in percentiles:
            idx = min(math.floor(p * f_size), f_size - 1)
            selected.append(bin_files[idx])
    return selected


def _get_html_names():
    """Get a sorted list of HTML file names from the datasets/html directory."""
    file_names = [file.name for file in Path("datasets/html").glob("*.html")]
    sorted_file_names = sorted(file_names, key=_file_name_sort_key_simple)
    return sorted_file_names


def build_config():
    """Generate a configuration JSON file that lists all HTML files and their metadata counts."""

    hierarchy_levels = ["modules", "nodes"]

    file_resolution_metrics = []  # 3D list: (file, resolution, hierarchy)
    file_names = _get_html_names()
    for html_name in file_names:
        with open("datasets/metadata/" + html_name.replace(".html", ".json"), "r", encoding="utf-8") as f:
            metadata = json.load(f)
            file_record = []
            for res_data in metadata.values():
                count_list = [len(res_data[key]) for key in hierarchy_levels]
                file_record.append(count_list)
            file_resolution_metrics.append(file_record)

    # Build the structure counts dictionary
    structure_counts = {}
    # Reshape to (resolution, hierarchy, file)
    structure_matrix = np.array(file_resolution_metrics).transpose((1, 2, 0))
    for r_index, res_data in enumerate(metadata.keys()):
        for h_index, hierarchy in enumerate(hierarchy_levels):
            structure_counts.setdefault(res_data, {})[hierarchy] = structure_matrix[r_index, h_index].tolist()

    # Average across files => (file, hierarchy)
    sample_mean = np.mean(file_resolution_metrics, axis=1)
    # Pair file names with their mean hierarchy counts, then sort by hierarchy counts (as tuples)
    sample_list = list(zip(file_names, sample_mean.tolist()))
    sorted_sample_list = sorted(sample_list, key=lambda x: x[1])  # x[1] is a list of hierarchy means
    filtered_sample_list = [name for name, counts in sorted_sample_list if counts[1] <= 50]
    selected_sample_list = _select_sample_files(filtered_sample_list)
    sorted_selected_sample_list = sorted(selected_sample_list, key=_file_name_sort_key_simple)

    with open("datasets/config.json", "w", encoding="utf-8") as f:
        config_data = {
            "html": file_names,
            "samples": sorted_selected_sample_list,
            **structure_counts,
        }
        json.dump(config_data, f, indent=2, ensure_ascii=False)


def build_report_data():
    """Generate a JSON file that contains the counts of modules, nodes, and their differences for each HTML file."""

    module_counts = []
    node_counts = []
    diff_counts = []
    file_names = _get_html_names()
    for html_name in file_names:
        with open("datasets/metadata/" + html_name.replace(".html", ".json"), "r", encoding="utf-8") as f:
            metadata = json.load(f)
            elements = list(metadata.values())

            module_count = np.mean([len(res_data["modules"]) for res_data in elements])
            module_counts.append(module_count)

            node_count = np.mean([len(res_data["nodes"]) for res_data in elements])
            node_counts.append(node_count)

            max_node_keys = set(elements[0]["nodes"].keys())
            min_node_keys = set(elements[-1]["nodes"].keys())
            diff_count = len(max_node_keys ^ min_node_keys)
            diff_counts.append(diff_count)

    combined_data = zip(file_names, module_counts, node_counts, diff_counts)
    sorted_data = sorted(combined_data, key=lambda x: (x[1], x[2]))  # Sort by module, then node

    output_path = Path("results/report/plot_data/dataset_page_complexity.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("file,module_count,node_count,diff_count\n")
        for file_name, module_count, node_count, diff_count in sorted_data:
            f.write(f"{file_name},{module_count},{node_count},{diff_count}\n")
    print(f"Report data saved to: {output_path}")


def _get_base_config(page_name: str) -> PageConfig:
    """Parse the file name to create a base PageConfig."""
    page_stem = Path(page_name).stem
    prototypes = get_html_prototypes(page_name)
    return PageConfig(
        root="",
        name=page_stem,
        url=f"http://localhost:{WEB_SERVER_PORT}/html/{page_stem}.html",
        metadata=f"datasets/metadata/{page_stem}.json",
        prototypes=prototypes,
        screenshots=prototypes,
    )


async def init_metadata() -> None:
    """Build metadata JSON files for a group items."""

    file_names = _get_html_names()
    async with launch_browser() as browser:
        with tqdm(file_names, dynamic_ncols=True, leave=True) as progress_bar:
            for file_name in progress_bar:
                progress_bar.set_description(file_name)

                base_config = _get_base_config(file_name)
                await generate_metadata(browser, base_config, overwrite=True)
                await capture_screenshots_with_browser(browser, base_config, overwrite=True)


def zip_datasets(folder_path: Path, file_path: Path) -> None:
    """Create a dataset archive from the dataset files."""
    try:
        exclude_folders = {"metadata", "screenshots"}
        with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in folder_path.rglob("*"):
                if file.is_file() and not any(part in exclude_folders for part in file.relative_to(folder_path).parts):
                    zipf.write(file, file.relative_to(folder_path))
                    print(f"Added: {file}")
        print(f"Dataset archive created: {file_path}")

    except OSError as e:
        print(f"Error creating dataset archive: {e}")


def unzip_datasets(folder_path: Path, file_path: Path) -> None:
    """Extract all files from the dataset archive."""
    try:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Dataset archive not found: {file_path}")

        with zipfile.ZipFile(file_path, "r") as zipf:
            zipf.extractall(folder_path)
            print(f"Extracted to: {folder_path}")

    except zipfile.BadZipFile:
        print("Error: The file is not a valid ZIP archive.")
    except OSError as e:
        print(f"Error extracting dataset archive: {e}")


if __name__ == "__main__":
    HELP_INFO = """
Dataset Management Script
Usage:
    python -m scripts.datasets action [zip|unzip|config|metadata|report]
"""
    # Initialize the parser
    parser = argparse.ArgumentParser(description=HELP_INFO)

    # Define the arguments
    parser.add_argument(
        "action",
        type=str,
        choices=["zip", "unzip", "config", "metadata", "report"],
        help="Action to perform: zip or unzip",
    )
    # Parse the arguments
    args = parser.parse_args()

    root_dir = Path(__file__).parent.parent
    dataset_folder = root_dir / "datasets"
    dataset_file = root_dir / "datasets.zip"

    if args.action == "config":
        # Build the dataset configuration file
        build_config()
    elif args.action == "metadata":
        # Create metadata JSON files and screenshots for the dataset
        asyncio.run(init_metadata())
    elif args.action == "report":
        # Build page complexity data for the report
        build_report_data()
    elif args.action == "zip":
        # Create dataset archive
        zip_datasets(dataset_folder, dataset_file)
    elif args.action == "unzip":
        # Unzip dataset
        unzip_datasets(dataset_folder, dataset_file)
