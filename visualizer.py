"""Generate a read-only visual map of a repository's latest commit."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import webbrowser

from git_reader import (
    GitRepositoryError,
    get_changes_for_commit,
    get_recent_commits,
    get_tracked_files,
    validate_repository,
)
from hierarchy import build_hierarchy
from treemap_renderer import VisualizationSnapshot, write_visualization


COMMIT_LIMIT = 10


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize recent repository commits as interactive treemaps."
    )
    parser.add_argument("repository", help="Path to a local Git working repository")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Generate the HTML without opening the default browser",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        started_at = perf_counter()
        repository = validate_repository(arguments.repository)
        commits = get_recent_commits(repository, limit=COMMIT_LIMIT)
        snapshots = []
        for commit in commits:
            tracked_files = get_tracked_files(repository, commit.full_hash)
            changes = get_changes_for_commit(repository, commit.full_hash)
            snapshots.append(
                VisualizationSnapshot(
                    commit=commit,
                    nodes=build_hierarchy(repository.name, tracked_files, changes),
                )
            )

        output_directory = Path(tempfile.mkdtemp(prefix="aiki-map-"))
        output_path = output_directory / "visualizer.html"
        write_visualization(snapshots, output_path)
        elapsed_seconds = perf_counter() - started_at
    except (GitRepositoryError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(output_path)
    print(
        f"{len(snapshots)} commits | {elapsed_seconds:.2f}s | "
        f"{output_path.stat().st_size / 1_000_000:.1f} MB"
    )
    if not arguments.no_open:
        webbrowser.open(output_path.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
