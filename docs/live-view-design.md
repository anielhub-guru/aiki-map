# Aiki Map Live View Design

## Purpose

AikiMap stays visible beside a coding agent and updates the working treemap
without requiring the user to rerun the command.

## Boundaries

- Codex can launch AikiMap through the installed `$aikimap` skill. Other IDEs
  can run `aikimap ide --detach`; terminal agents can use wrapper commands.
- The server binds only to `127.0.0.1`.
- Git access remains read-only.
- The browser checks for changes every 2.5 seconds.
- The treemap redraws only when its repository state changes.
- The existing standalone output remains available through `--static`.
- Native agent sessions open in a compact ambient mode. Review expands the same
  local interface rather than opening a second application surface.
- Treemap geometry does not animate. The live-edit AikiBot uses a small motion
  cue; commit-history AikiBot markers remain static and visible.

## Data flow

1. Python reads the working state and recent commit metadata.
2. The local server embeds only the working trace in the first HTML response.
3. The browser sends its current state version to `/api/state` every 2.5 seconds.
4. The server returns `304 Not Modified` when the visual state is unchanged.
5. When the state differs, the server returns the working trace and snapshot metadata.
6. History navigation requests one authenticated commit trace at a time; the
   browser replaces the current trace and discards the preceding one.

If `HEAD` changes, the server rebuilds recent history. If a refresh fails, the
browser keeps the last valid map visible, reports the problem, and retries.

## File inspection

Folder clicks continue to drill into the treemap. Selecting a file temporarily
turns that file's own rectangle into a read-only inspector with its
repository-relative path, exact Git state, comparison basis, and added/deleted
line totals. The initial map remains unchanged until a file is selected. Patch
content is requested separately only after Show Diff is selected. The inspector
uses the expanded rectangle's full width and height and scrolls internally when
needed; the treemap breadcrumb or view controls leave the selected file.

The server accepts a file only when its path exists as a visible file node in the
requested snapshot. Working diffs separate staged and unstaged changes; commit
diffs compare the selected commit with the same baseline used by the map.
Repository content is inserted into the page through text nodes, not executable
HTML. Added and removed lines receive muted green and red treatments while their
Git `+` and `-` prefixes remain visible, so colour is not the only signal. Hunk
markers and patch metadata remain visually secondary. Binary files receive a
clear label, and textual patches stop after 2,000 lines or 200 KB.

## Decision log

- Live mode is the default because current changes are the primary product value.
- Polling was selected over filesystem watching because a 2–3 second delay is
  acceptable and polling is simpler and more portable.
- Responses are versioned so unchanged polls do not transfer or redraw map data.
- Native/live mode keeps one Plotly trace in the WebView to bound document size,
  DOM work, and memory use on large repositories.
- The server uses Python's standard library to avoid another runtime dependency.
- Spatial animation is deferred unless a future renderer can reliably preserve
  rectangle identity while boxes move, grow, and shrink.
- File diffs are on-demand because verification is core product value, while
  computing every patch during live polling would add avoidable work.
- File inspection stays inside the selected rectangle so location and
  verification remain in the same visual context without reserving page width.
- Ambient mode prioritizes session state, the changed-file count, and the live
  treemap. History controls, the full legend, and detailed inspection appear in
  the expanded Review mode where they have sufficient space.
