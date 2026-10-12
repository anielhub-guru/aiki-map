"""Build and cache visualization snapshots from read-only Git data."""

from __future__ import annotations

from pathlib import Path
from time import monotonic

from git_reader import (
    CommitInfo,
    get_branches,
    get_changes_for_commit,
    get_latest_commit,
    get_recent_commits,
    get_tracked_files,
    get_working_changes,
)
from hierarchy import HierarchyNode, build_hierarchy
from treemap_renderer import VisualizationSnapshot


class SnapshotBuilder:
    """Reuse immutable commit snapshots while refreshing the working tree."""

    def __init__(self, repository: Path, commit_limit: int = 10) -> None:
        self.repository = repository
        self.commit_limit = commit_limit
        self._head_hash = ""
        self._head_files: list[str] = []
        self._history: list[VisualizationSnapshot] = []
        self._working_signatures: dict[str, tuple[int, int] | None] | None = None
        self._activity_paths: tuple[str, ...] = ()
        self._activity_revision = 0
        self._activity_expires_at = 0.0
        self._branch_history_tip = ""
        self._branch_history: list[VisualizationSnapshot] = []

    def load(self, history_ref: str = "") -> list[VisualizationSnapshot]:
        if not self._history:
            self._reload_history()
        else:
            latest_commit = get_latest_commit(self.repository)
            if latest_commit.full_hash != self._head_hash:
                self._reload_history()

        head_commit = self._history[0].commit
        branches = get_branches(self.repository)
        selected_branch = next((branch for branch in branches if branch.ref == history_ref), None)
        history_ref = selected_branch.ref if selected_branch and not selected_branch.current else ""
        history = self._history
        if history_ref:
            if selected_branch.tip != self._branch_history_tip:
                self._branch_history = self._build_history(
                    get_recent_commits(self.repository, self.commit_limit, selected_branch.tip)
                )
                self._branch_history_tip = selected_branch.tip
            history = self._branch_history
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
        signatures = self._file_signatures(working_nodes)
        if self._working_signatures is not None:
            changed_paths = tuple(
                sorted(
                    path
                    for path, signature in signatures.items()
                    if self._working_signatures.get(path) != signature
                )
            )
            if changed_paths:
                self._activity_paths = changed_paths
                self._activity_revision += 1
                self._activity_expires_at = monotonic() + 6.0
            elif monotonic() >= self._activity_expires_at:
                self._activity_paths = ()
        self._working_signatures = signatures
        working_snapshot = VisualizationSnapshot(
            commit=head_commit,
            nodes=working_nodes,
            kind="working",
            change_count=working_change_count,
            activity_paths=self._activity_paths,
            activity_revision=self._activity_revision,
            branches=tuple(branches),
            history_ref=history_ref,
        )
        return [working_snapshot, *history]

    def _file_signatures(
        self,
        nodes: list[HierarchyNode],
    ) -> dict[str, tuple[int, int] | None]:
        signatures = {}
        for node in nodes:
            if node.kind != "file":
                continue
            try:
                stat = (self.repository / node.path).stat()
                signatures[node.path] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                signatures[node.path] = None
        return signatures

    def _reload_history(self) -> None:
        commits = get_recent_commits(self.repository, limit=self.commit_limit)
        head_commit = commits[0]
        head_files = get_tracked_files(self.repository, head_commit.full_hash)
        history = self._build_history(commits)

        self._head_hash = head_commit.full_hash
        self._head_files = head_files
        self._history = history

    def _build_history(self, commits: list[CommitInfo]) -> list[VisualizationSnapshot]:
        history = []

        for commit in commits:
            tracked_files = get_tracked_files(self.repository, commit.full_hash)
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

        return history
