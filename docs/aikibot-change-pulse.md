# AikiBot Change Markers

## Understanding

- Review navigation should immediately draw attention to changed files.
- The existing robot-face SVG is the visual marker and is named **AikiBot**.
- Review mode uses persistent **AikiBot change markers** rather than a timed animation.
- Markers remain visible for the selected commit and reposition after rendering or resize.
- Rapid Older/Newer navigation cancels stale responses without blocking either button.
- Existing live-edit robots remain independent and continue showing fresh edits.
- Performance must remain suitable for large repository maps.

## Assumptions

- Snapshot traces already contain every file path, type, and change status needed.
- Hidden file tiles may be represented by their nearest visible folder.
- Large change sets may be grouped to bound simultaneous marker elements.
- Live mode should retain only the selected Plotly trace in the WebView.

## Options considered

1. Persistent inline SVG markers — selected because they are deterministic, visible
   until navigation, and add no image decoding or animation timers.
2. Timed SVG or GIF animation — rejected after native WebView timing and visibility
   proved unreliable and added layout work without dependable user value.
3. Draw robots into the Plotly trace — rejected because it couples markers to chart
   recalculation and makes live and review activity harder to separate.

## Decision log

- Use the name **AikiBot change markers**.
- Render in a dedicated overlay so live-edit indicators are not interrupted.
- Keep the overlay pointer-transparent and replace markers on every new selection.
- Position markers from `plotly_afterplot` and explicit resize completion.
- Use changed-file status already present in the active trace.
- Group large or hidden change sets by visible top-level folders.
- Hydrate and return one requested history trace through the local authenticated API.

## Large-repository correction

### Understanding

- Keeping ten complete Plotly traces in a native WebView increases document size and rendering work.
- Measuring every rendered tile delays the attention effect and adds layout work.
- Polling currently stats every tracked file, including files Git already reports as unchanged.
- Rapid navigation and the 2.5-second live-update cadence must remain unchanged.
- The fix must not add dependencies, API calls, or a new rendering architecture.

### Options considered

1. Lazy-load one commit trace — selected because it removes the dominant native
   WebView payload and keeps navigation data small.
2. Keep all traces and tune animation delays — rejected because it preserves the
   unreliable behavior and the avoidable rendering cost.
3. Port the backend to Rust — rejected because it would not reduce Plotly/WebKit work.

### Decisions

- Use `Plotly.react` with one trace and ignore stale snapshot responses.
- Scan slice metadata but call `getBoundingClientRect()` only for candidate anchors.
- Track signatures only for files Git marks changed and compare both old and new keys.
- Keep commit metadata in memory but build each commit hierarchy only when requested.
