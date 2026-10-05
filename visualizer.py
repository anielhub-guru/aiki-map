"""Generate a read-only visual map of working changes and recent commits."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import webbrowser

from git_reader import GitRepositoryError, validate_repository
from live_server import serve_live
from snapshot_builder import SnapshotBuilder
from treemap_renderer import write_visualization


COMMIT_LIMIT = 10


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize working changes and recent commits as interactive treemaps."
    )
    parser.add_argument("repository", help="Path to a local Git working repository")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser automatically",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="Generate a standalone HTML file instead of starting live mode",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        started_at = perf_counter()
        repository = validate_repository(arguments.repository)
        builder = SnapshotBuilder(repository, commit_limit=COMMIT_LIMIT)

        if not arguments.static:
            serve_live(builder, open_browser=not arguments.no_open)
            return 0

        snapshots = builder.load()
        output_directory = Path(tempfile.mkdtemp(prefix="aiki-map-"))
        output_path = output_directory / "visualizer.html"
        write_visualization(snapshots, output_path)
        elapsed_seconds = perf_counter() - started_at
    except (GitRepositoryError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(output_path)
    print(
        f"{snapshots[0].change_count} working changes | "
        f"{len(snapshots) - 1} commits | "
        f"{elapsed_seconds:.2f}s | "
        f"{output_path.stat().st_size / 1_000_000:.1f} MB"
    )
    if not arguments.no_open:
        webbrowser.open(output_path.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
