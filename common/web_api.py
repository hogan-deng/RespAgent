"""This module provides a series of tools for running the web API."""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from common.browser import Browser, launch_browser
from common.config import RESOLUTION_LIST
from common.json_output import json_serializable
from common.score import evaluate_metadata
from metrics.dom_snapshot import PageElements, SnapshotDocument
from metrics.utils.typings import PriorConfig


load_dotenv()
WEB_SERVER_PORT = int(os.getenv("PORT", "8000"))


async def _generate_metadata(
    browser: Browser,
    page_url: str,
    prior_list: list[list],
) -> dict[str, PageElements]:
    """Generate and save the metadata JSON file using an existing Browser instance."""

    # Validate viewport configuration
    resolutions = [f"{s[0]}x{s[1]}" for s in RESOLUTION_LIST]

    include_modules = set(prior_list[0]) if len(prior_list) > 0 else set()
    exclude_nodes = set(prior_list[1]) if len(prior_list) > 1 else set()
    merge_modules = prior_list[2] if len(prior_list) > 2 else []
    prior_config = PriorConfig(
        include_modules=include_modules, exclude_nodes=exclude_nodes, merge_modules=merge_modules
    )

    # Generate metadata for each viewport
    metadata: dict[str, PageElements] = {}
    for res in resolutions:
        # Capture snapshot and extract elements
        snapshot_document = await SnapshotDocument.create(browser, page_url, res, prior_config)
        metadata[res] = snapshot_document.export_element_data()

    return metadata


async def rebuild_manual_score(file_name: str, root_path: str, base_prior: list, eval_prior: list) -> None:
    """Rebuild the manual score for a given file."""

    root_path = root_path.lstrip("/")  # Remove leading slash if present
    base_url = f"http://localhost:{WEB_SERVER_PORT}/html/{file_name}"
    eval_url = f"http://localhost:{WEB_SERVER_PORT}/{root_path}/{file_name}"

    async with launch_browser() as browser:
        # Generate metadata for the base and evaluation URLs
        base_metadata = await _generate_metadata(browser, base_url, base_prior)
        eval_metadata = await _generate_metadata(browser, eval_url, eval_prior)

        comparison_results = evaluate_metadata(base_metadata, eval_metadata, disable_merge=True)
        comparison_results["manual_config"] = {
            "base_prior": base_prior,
            "eval_prior": eval_prior,
        }

        manual_score_path = Path(f"results/{root_path}/manual_score/" + file_name.replace(".html", ".json"))
        manual_score_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manual_score_path, "w", encoding="utf-8") as f:
            json.dump(comparison_results, f, default=json_serializable, indent=2)
            print(f"Manual score saved to {manual_score_path}")


async def rebuild_auto_score(file_name: str, root_path: str) -> None:
    """Rebuild the auto score for a given file."""

    root_path = root_path.lstrip("/")  # Remove leading slash if present
    base_url = f"http://localhost:{WEB_SERVER_PORT}/html/{file_name}"
    eval_url = f"http://localhost:{WEB_SERVER_PORT}/{root_path}/{file_name}"

    async with launch_browser() as browser:
        # Generate metadata for the evaluation URL
        base_metadata = await _generate_metadata(browser, base_url, [])
        eval_metadata = await _generate_metadata(browser, eval_url, [])

        comparison_results = evaluate_metadata(base_metadata, eval_metadata)
        auto_score_path = Path(f"results/{root_path}/auto_score/" + file_name.replace(".html", ".json"))
        auto_score_path.parent.mkdir(parents=True, exist_ok=True)
        with open(auto_score_path, "w", encoding="utf-8") as f:
            json.dump(comparison_results, f, default=json_serializable, indent=2)
            print(f"Auto score saved to {auto_score_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh auto score for a given file.")
    parser.add_argument(
        "action",
        choices=["rebuild_manual_score", "rebuild_auto_score"],
        help="The action to perform.",
    )
    parser.add_argument(
        "--file_name", type=str, required=True, help="The name of the file to refresh the auto score for."
    )
    parser.add_argument(
        "--root_path",
        type=str,
        help="The root path where metadata and auto_score directories are located.",
    )
    parser.add_argument(
        "--base_prior",
        type=json.loads,
        help="A JSON object containing base priority for manual score rebuilding.",
    )
    parser.add_argument(
        "--eval_prior",
        type=json.loads,
        help="A JSON object containing evaluation priority for manual score rebuilding.",
    )
    args = parser.parse_args()

    if args.action == "rebuild_manual_score":
        asyncio.run(rebuild_manual_score(args.file_name, args.root_path, args.base_prior, args.eval_prior))
    elif args.action == "rebuild_auto_score":
        asyncio.run(rebuild_auto_score(args.file_name, args.root_path))
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)
