"""Read committed repository information without modifying Git state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


READ_ONLY_COMMANDS = {
    "diff-tree",
    "log",
    "ls-tree",
    "rev-list",
    "rev-parse",
    "show",
}


class GitRepositoryError(RuntimeError):
    """Raised when a repository cannot provide the requested information."""


@dataclass(frozen=True)
class CommitInfo:
    full_hash: str
    short_hash: str
    message: str
    author: str
    authored_at: str


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    previous_path: str | None = None


def _run_git(repository: Path, *arguments: str) -> str:
    if not arguments or arguments[0] not in READ_ONLY_COMMANDS:
        raise ValueError("Only approved read-only Git commands may be used")

    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Git command failed"
        raise GitRepositoryError(message)
    return result.stdout


def validate_repository(repository: str | Path) -> Path:
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise GitRepositoryError(f"Repository directory does not exist: {path}")

    inside_work_tree = _run_git(path, "rev-parse", "--is-inside-work-tree").strip()
    is_bare = _run_git(path, "rev-parse", "--is-bare-repository").strip()
    if inside_work_tree != "true" or is_bare == "true":
        raise GitRepositoryError("A non-bare Git working repository is required")

    return path


def get_tracked_files(repository: Path, revision: str = "HEAD") -> list[str]:
    """Return the file paths stored in a committed snapshot."""
    output = _run_git(repository, "ls-tree", "-r", "--name-only", "-z", revision)
    return [path for path in output.split("\0") if path]


def get_recent_commits(repository: Path, limit: int = 10) -> list[CommitInfo]:
    if limit < 1:
        raise ValueError("Commit limit must be at least 1")

    field_separator = "%x1f"
    record_separator = "%x1e"
    output = _run_git(
        repository,
        "log",
        "-n",
        str(limit),
        (
            f"--format=%H{field_separator}%h{field_separator}%s"
            f"{field_separator}%an{field_separator}%aI{record_separator}"
        ),
    )
    commits = []
    for record in output.split("\x1e"):
        fields = record.strip().split("\x1f")
        if fields == [""]:
            continue
        if len(fields) != 5:
            raise GitRepositoryError("Could not parse commit history metadata")
        commits.append(
            CommitInfo(
                full_hash=fields[0],
                short_hash=fields[1],
                message=fields[2],
                author=fields[3],
                authored_at=fields[4],
            )
        )

    if not commits:
        raise GitRepositoryError("The repository has no commits")
    return commits


def get_latest_commit(repository: Path) -> CommitInfo:
    return get_recent_commits(repository, limit=1)[0]


def get_latest_changes(repository: Path) -> list[FileChange]:
    return get_changes_for_commit(repository, "HEAD")


def get_changes_for_commit(repository: Path, revision: str) -> list[FileChange]:
    commit_and_parents = _run_git(
        repository, "rev-list", "--parents", "-n", "1", revision
    ).split()
    if not commit_and_parents:
        raise GitRepositoryError("The repository has no commits")

    commit_hash = commit_and_parents[0]
    if len(commit_and_parents) == 1:
        arguments = (
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-M",
            "-z",
            commit_hash,
        )
    else:
        arguments = (
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "-M",
            "-z",
            commit_and_parents[1],
            commit_hash,
        )

    return _parse_name_status(_run_git(repository, *arguments))


def _parse_name_status(output: str) -> list[FileChange]:
    fields = [field for field in output.split("\0") if field]
    changes: list[FileChange] = []
    index = 0

    while index < len(fields):
        raw_status = fields[index]
        index += 1
        status = raw_status[0]

        if status in {"R", "C"}:
            if index + 1 >= len(fields):
                raise GitRepositoryError("Could not parse a renamed or copied path")
            previous_path, path = fields[index], fields[index + 1]
            index += 2
            changes.append(FileChange(status=status, path=path, previous_path=previous_path))
            continue

        if index >= len(fields):
            raise GitRepositoryError("Could not parse a changed path")
        changes.append(FileChange(status=status, path=fields[index]))
        index += 1

    return changes
