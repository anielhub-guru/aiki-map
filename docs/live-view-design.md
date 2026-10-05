# Aiki Map Live View Design

## Purpose

V0.2 keeps Aiki Map visible beside an AI coding tool and updates the working
treemap without requiring the user to rerun the command.

## Boundaries

- The terminal remains the launch point.
- The server binds only to `127.0.0.1`.
- Git access remains read-only.
- The browser checks for changes every 2.5 seconds.
- The treemap redraws only when its repository state changes.
- The existing standalone output remains available through `--static`.
- There are no animations. Plotly does not smoothly interpolate treemap
  geometry, and substitute fades do not serve the intended interaction.
- Codex and plugin integration remain outside V0.2.

## Data flow

1. Python reads the current working state and recent commit history.
2. The local server embeds the initial snapshots in the first HTML response.
3. The browser sends its current state version to `/api/state` every 2.5 seconds.
4. The server returns `304 Not Modified` when the visual state is unchanged.
5. When the state differs, the server returns replacement Plotly traces and
   snapshot metadata.
6. The browser redraws immediately and retains the user's selected view.

If `HEAD` changes, the server rebuilds recent history. If a refresh fails, the
browser keeps the last valid map visible, reports the problem, and retries.

## Decision log

- Live mode is the default because current changes are the primary product value.
- Polling was selected over filesystem watching because a 2–3 second delay is
  acceptable and polling is simpler and more portable.
- Responses are versioned so unchanged polls do not transfer or redraw map data.
- The server uses Python's standard library to avoid another runtime dependency.
- Spatial animation is deferred unless a future renderer can reliably preserve
  rectangle identity while boxes move, grow, and shrink.
