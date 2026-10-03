# Aiki Map

Aiki Map is a read-only terminal tool that generates an interactive
treemap of a local repository. It highlights files changed by each of the latest
10 commits and shows where those files sit within the committed repository structure.

## What it does

- Reads the latest 10 committed snapshots through the Git CLI
- Compares each commit with its first parent
- Distinguishes added, modified, deleted, renamed, and unchanged files
- Navigates backward and forward through the loaded commits
- Excludes common dependency, build, cache, and editor directories
- Generates a self-contained `visualizer.html` in a temporary directory
- Opens the visualization in the default browser

## What it does not do

- Modify repository files or Git state
- Stage, commit, switch, reset, or restore anything
- Display source code or code diffs
- Run a web server or contact an external service
- Include untracked or ignored files
- Load more than 10 commits or watch for new commits

## Requirements

- Python 3.10 or newer
- Git available on the command line

Install the Python dependency:

```bash
python -m pip install -r requirements.txt
```

## Usage

```bash
python visualizer.py /path/to/repository
```

Generate the file without opening a browser:

```bash
python visualizer.py /path/to/repository --no-open
```

The command prints the temporary path containing `visualizer.html`. The
operating system may remove that directory during later temporary-file cleanup.
It also prints the number of embedded commits, generation time, and HTML size.

## Read-only Git commands

The implementation permits only these observational Git commands:

- `git rev-parse`
- `git rev-list`
- `git log`
- `git ls-tree`
- `git show`
- `git diff-tree`
