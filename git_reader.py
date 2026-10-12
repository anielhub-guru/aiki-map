"""Read committed repository information without modifying Git state."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from pathlib import PurePosixPath
import subprocess


READ_ONLY_COMMANDS = {
    "diff",
    "diff-tree",
    "for-each-ref",
    "log",
    "ls-tree",
    "rev-list",
    "rev-parse",
    "show",
    "status",
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
class BranchInfo:
    ref: str
    name: str
    tip: str
    current: bool
    remote: bool


def get_branches(repository: Path) -> list[BranchInfo]:
    """Read local and fetched remote branches without switching the checkout."""
    output = _run_git(
        repository, "for-each-ref",
        "--format=%(refname)\t%(objectname)\t%(HEAD)\t%(symref)",
        "refs/heads/", "refs/remotes/",
    )
    branches = []
    for line in output.splitlines():
        ref, tip, current, symbolic = line.split("\t")
        if symbolic:
            continue
        remote = ref.startswith("refs/remotes/")
        prefix = "refs/remotes/" if remote else "refs/heads/"
        branches.append(BranchInfo(ref, ref.removeprefix(prefix), tip, current == "*", remote))
    return branches


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    previous_path: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class FileDiffStats:
    additions: int
    deletions: int
    binary: bool


@dataclass(frozen=True)
class FileDiffSection:
    label: str
    content: str


def _run_git(
    repository: Path,
    *arguments: str,
    acceptable_returncodes: tuple[int, ...] = (0,),
) -> str:
    if not arguments or arguments[0] not in READ_ONLY_COMMANDS:
        raise ValueError("Only approved read-only Git commands may be used")

    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode not in acceptable_returncodes:
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


def get_recent_commits(
    repository: Path, limit: int = 10, revision: str = "HEAD"
) -> list[CommitInfo]:
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
        revision,
        "--",
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


def get_working_changes(repository: Path) -> list[FileChange]:
    output = _run_git(
        repository,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--renames",
    )
    return _parse_working_status(output)


def get_working_file_stats(
    repository: Path,
    path: str,
    untracked: bool = False,
) -> FileDiffStats:
    safe_path = _validate_relative_path(path)
    if untracked:
        output = _run_git(
            repository,
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--numstat",
            "--",
            os.devnull,
            safe_path,
            acceptable_returncodes=(0, 1),
        )
    else:
        output = _run_git(
            repository,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--numstat",
            "HEAD",
            "--",
            safe_path,
        )
    return _parse_numstat(output)


def get_working_file_diff(
    repository: Path,
    path: str,
    untracked: bool = False,
) -> list[FileDiffSection]:
    safe_path = _validate_relative_path(path)
    if untracked:
        patch = _run_git(
            repository,
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--no-textconv",
            "--",
            os.devnull,
            safe_path,
            acceptable_returncodes=(0, 1),
        )
        return [FileDiffSection(label="Untracked file", content=patch)]

    sections = []
    staged = _run_git(
        repository,
        "diff",
        "--cached",
        "--no-ext-diff",
        "--no-textconv",
        "--",
        safe_path,
    )
    unstaged = _run_git(
        repository,
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--",
        safe_path,
    )
    if staged:
        sections.append(FileDiffSection(label="Staged changes", content=staged))
    if unstaged:
        sections.append(FileDiffSection(label="Unstaged changes", content=unstaged))
    return sections


def get_commit_file_stats(
    repository: Path,
    revision: str,
    path: str,
) -> FileDiffStats:
    arguments = _commit_file_arguments(repository, revision, path, "--numstat")
    return _parse_numstat(_run_git(repository, *arguments))


def get_commit_file_diff(
    repository: Path,
    revision: str,
    path: str,
) -> list[FileDiffSection]:
    arguments = _commit_file_arguments(repository, revision, path)
    patch = _run_git(repository, *arguments)
    return [FileDiffSection(label="Committed changes", content=patch)] if patch else []


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


def _parse_working_status(output: str) -> list[FileChange]:
    fields = output.split("\0")
    changes: list[FileChange] = []
    index = 0

    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            raise GitRepositoryError("Could not parse working-tree status")

        code = record[:2]
        path = record[3:]
        previous_path = None
        if "R" in code or "C" in code:
            if index >= len(fields) or not fields[index]:
                raise GitRepositoryError("Could not parse a working-tree rename")
            previous_path = fields[index]
            index += 1

        changes.append(
            FileChange(
                status=_working_change_status(code),
                path=path,
                previous_path=previous_path,
                detail=_working_change_detail(code),
            )
        )

    return changes


def _working_change_status(code: str) -> str:
    if code == "??":
        return "A"
    for status in ("D", "R", "C", "A", "M", "T", "U"):
        if status in code:
            return "M" if status == "U" else status
    return "M"


def _working_change_detail(code: str) -> str:
    if code == "??":
        return "Untracked"

    labels = []
    if code[0] != " ":
        labels.append(f"Staged {_status_description(code[0])}")
    if code[1] != " ":
        labels.append(f"Unstaged {_status_description(code[1])}")
    return " + ".join(labels)


def _status_description(status: str) -> str:
    return {
        "A": "addition",
        "C": "copy",
        "D": "deletion",
        "M": "modification",
        "R": "rename",
        "T": "type change",
        "U": "unmerged change",
    }.get(status, "change")


def _commit_file_arguments(
    repository: Path,
    revision: str,
    path: str,
    *options: str,
) -> tuple[str, ...]:
    safe_path = _validate_relative_path(path)
    commit_and_parents = _run_git(
        repository,
        "rev-list",
        "--parents",
        "-n",
        "1",
        revision,
    ).split()
    if not commit_and_parents:
        raise GitRepositoryError("The repository has no commits")
    commit_hash = commit_and_parents[0]
    if len(commit_and_parents) == 1:
        return (
            "show",
            "--format=",
            "--no-ext-diff",
            "--no-textconv",
            "-M",
            *options,
            commit_hash,
            "--",
            safe_path,
        )
    return (
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "-M",
        *options,
        commit_and_parents[1],
        commit_hash,
        "--",
        safe_path,
    )


def _parse_numstat(output: str) -> FileDiffStats:
    additions = 0
    deletions = 0
    binary = False
    for line in output.splitlines():
        fields = line.split("\t", 2)
        if len(fields) < 3:
            continue
        if fields[0] == "-" or fields[1] == "-":
            binary = True
            continue
        additions += int(fields[0])
        deletions += int(fields[1])
    return FileDiffStats(
        additions=additions,
        deletions=deletions,
        binary=binary,
    )


def _validate_relative_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or "\0" in path
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise ValueError("A repository-relative file path is required")
    return candidate.as_posix()
