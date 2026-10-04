# Aiki Map

See what changed in your AI-assisted coding workflow—at a glance.

AI coding tools can modify more of a repository than you expected. Aiki Map turns
recent Git commits into an interactive visual map, making it easier to spot which
files changed and where they sit in the project before you continue building.

![Aiki Map visualizing a modified file in a mock repository](docs/aiki-map-demo.png)

## What the map shows

- Each rectangle represents a tracked file.
- Folder size reflects the number of files it contains—not lines of code or complexity.
- Changed folders are highlighted so you can locate affected areas quickly.
- Older and newer controls let you inspect up to 10 recent commits.

| Colour | Meaning |
| --- | --- |
| Cool grey | Unchanged |
| Pale lavender | Folder contains changes |
| Muted teal | Added |
| Amber | Modified |
| Coral | Deleted |
| Indigo | Renamed |

## Quick start

You need Python 3.10 or newer and Git on your command line.

```bash
git clone https://github.com/anielhub-guru/aiki-map.git
cd aiki-map
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python visualizer.py /path/to/repository
```

Aiki Map creates `visualizer.html` in a temporary directory, prints its location
and generation time, then opens it in your default browser.

To generate the file without opening a browser:

```bash
python visualizer.py /path/to/repository --no-open
```

## Read-only by design

Aiki Map observes committed Git history without modifying the repository it
inspects. It does not stage files, create commits, switch branches, restore files,
or change Git configuration. The generated HTML is written outside the inspected
repository and works without a server or external service.

## How it works

1. Read metadata for the latest 10 commits.
2. Compare each commit with its first parent.
3. Build the repository hierarchy from tracked files.
4. Mark added, modified, deleted, and renamed paths.
5. Embed the commit snapshots in one standalone interactive HTML file.

Common dependency, build, cache, and editor directories are filtered from the map
so that application structure remains visible.

## Current scope

The current MVP visualizes committed history. It does not yet show uncommitted
working changes or line-by-line code differences. A working-changes view is being
evaluated for a later iteration.
