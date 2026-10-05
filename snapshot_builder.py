"""Build and cache visualization snapshots from read-only Git data."""

from __future__ import annotations

from pathlib import Path

from git_reader import (
    get_changes_for_commit,
    get_latest_commit,
    get_recent_commits,
    get_tracked_files,
    get_working_changes,
)
from hierarchy import build_hierarchy
from treemap_renderer import VisualizationSnapshot


class SnapshotBuilder:
    """Reuse immutable commit snapshots while refreshing the working tree."""

    def __init__(self, repository: Path, commit_limit: int = 10) -> None:
        self.repository = repository
        self.commit_limit = commit_limit
        self._head_hash = ""
        self._head_files: list[str] = []
        self._history: list[VisualizationSnapshot] = []

    def load(self) -> list[VisualizationSnapshot]:
        if not self._history:
            self._reload_history()
        else:
            latest_commit = get_latest_commit(self.repository)
            if latest_commit.full_hash != self._head_hash:
                self._reload_history()

        head_commit = self._history[0].commit
        working_changes = get_working_changes(self.repository)
        working_nodes = build_hierarchy(
            self.repository.name,
            self._head_files,
            working_changes,
        )
        working_change_count = sum(
            node.kind == "file" and node.status != "unchanged"
            for node in working_nodes
        )
        working_snapshot = VisualizationSnapshot(
            commit=head_commit,
            nodes=working_nodes,
            kind="working",
            change_count=working_change_count,
        )
        return [working_snapshot, *self._history]

    def _reload_history(self) -> None:
        commits = get_recent_commits(self.repository, limit=self.commit_limit)
        head_commit = commits[0]
        head_files = get_tracked_files(self.repository, head_commit.full_hash)
        history = []

        for commit in commits:
            tracked_files = (
                head_files
                if commit.full_hash == head_commit.full_hash
                else get_tracked_files(self.repository, commit.full_hash)
            )
            changes = get_changes_for_commit(self.repository, commit.full_hash)
            history.append(
                VisualizationSnapshot(
                    commit=commit,
                    nodes=build_hierarchy(
                        self.repository.name,
                        tracked_files,
                        changes,
                    ),
                )
            )

        self._head_hash = head_commit.full_hash
        self._head_files = head_files
        self._history = history
