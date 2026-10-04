"""Convert flat Git paths into visualization-ready hierarchy nodes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from git_reader import FileChange


STATUS_NAMES = {
    "A": "added",
    "C": "added",
    "D": "deleted",
    "M": "modified",
    "R": "renamed",
    "T": "modified",
}

IGNORED_PATH_PARTS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}

IGNORED_FILE_NAMES = {".DS_Store"}


@dataclass(frozen=True)
class HierarchyNode:
    node_id: str
    label: str
    parent_id: str
    kind: str
    status: str
    value: int
    path: str
    previous_path: str | None = None
    detail: str = ""


def build_hierarchy(
    repository_name: str,
    tracked_files: Iterable[str],
    changes: Iterable[FileChange],
) -> list[HierarchyNode]:
    """Build repository, folder, and file nodes from committed Git paths."""
    changes_by_path = {
        change.path: change for change in changes if not _is_ignored(change.path)
    }
    file_paths = {
        _validate_git_path(path) for path in tracked_files if not _is_ignored(path)
    }

    for change in changes_by_path.values():
        file_paths.add(_validate_git_path(change.path))
        if change.previous_path and change.status in {"R", "C"}:
            file_paths.discard(_validate_git_path(change.previous_path))

    folder_paths: set[str] = set()
    for file_path in file_paths:
        parent = PurePosixPath(file_path).parent
        while parent != PurePosixPath("."):
            folder_paths.add(parent.as_posix())
            parent = parent.parent

    nodes = [_build_root(repository_name, file_paths, changes_by_path)]
    nodes.extend(
        _build_folder(folder_path, file_paths, changes_by_path)
        for folder_path in sorted(folder_paths, key=lambda path: (path.count("/"), path))
    )
    nodes.extend(
        _build_file(file_path, changes_by_path.get(file_path))
        for file_path in sorted(file_paths)
    )
    return nodes


def _build_root(
    repository_name: str,
    file_paths: set[str],
    changes_by_path: dict[str, FileChange],
) -> HierarchyNode:
    return HierarchyNode(
        node_id="repo:/",
        label=repository_name,
        parent_id="",
        kind="repository",
        status=_container_status(file_paths, changes_by_path),
        value=len(file_paths),
        path="",
    )


def _build_folder(
    folder_path: str,
    file_paths: set[str],
    changes_by_path: dict[str, FileChange],
) -> HierarchyNode:
    contained_files = {
        path for path in file_paths if path.startswith(f"{folder_path}/")
    }
    parent_path = PurePosixPath(folder_path).parent.as_posix()
    parent_id = "repo:/" if parent_path == "." else f"dir:{parent_path}"
    return HierarchyNode(
        node_id=f"dir:{folder_path}",
        label=PurePosixPath(folder_path).name,
        parent_id=parent_id,
        kind="folder",
        status=_container_status(contained_files, changes_by_path),
        value=len(contained_files),
        path=folder_path,
    )


def _build_file(file_path: str, change: FileChange | None) -> HierarchyNode:
    parent_path = PurePosixPath(file_path).parent.as_posix()
    parent_id = "repo:/" if parent_path == "." else f"dir:{parent_path}"
    return HierarchyNode(
        node_id=f"file:{file_path}",
        label=PurePosixPath(file_path).name,
        parent_id=parent_id,
        kind="file",
        status=_change_status(change),
        value=1,
        path=file_path,
        previous_path=change.previous_path if change else None,
        detail=change.detail if change else "",
    )


def _container_status(
    contained_files: Iterable[str],
    changes_by_path: dict[str, FileChange],
) -> str:
    return (
        "changed"
        if any(path in changes_by_path for path in contained_files)
        else "unchanged"
    )


def _change_status(change: FileChange | None) -> str:
    if change is None:
        return "unchanged"
    return STATUS_NAMES.get(change.status, "modified")


def _validate_git_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Invalid repository-relative Git path: {path!r}")
    return candidate.as_posix()


def _is_ignored(path: str) -> bool:
    candidate = PurePosixPath(path)
    return (
        candidate.name in IGNORED_FILE_NAMES
        or any(part in IGNORED_PATH_PARTS for part in candidate.parts)
    )
