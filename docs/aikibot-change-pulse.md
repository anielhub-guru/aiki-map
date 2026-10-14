# AikiBot Change Pulse

## Understanding

- Review navigation should immediately draw attention to changed files.
- The existing robot-face SVG is the visual marker and is named **AikiBot**.
- The short review animation is named **AikiBot Change Pulse**.
- It runs on initial display and explicit snapshot or branch navigation.
- Automatic live polling must not replay it.
- Rapid Older/Newer navigation must remain clickable and must not stack pulses.
- Existing live-edit robots remain independent and continue showing fresh edits.
- Performance must remain suitable for large repository maps.

## Assumptions

- Snapshot traces already contain every file path, type, and change status needed.
- A pulse should finish in approximately 1.5 seconds.
- Hidden file tiles may be represented by their nearest visible folder.
- Large change sets may be grouped to bound simultaneous animated elements.
- Reduced-motion users should receive a brief static highlight without movement.

## Options considered

1. Reuse the inline SVG and DOM overlay — selected because it adds no dependency,
   image decode, network request, or new backend work.
2. Add an animated GIF — rejected because it is less adaptable, heavier, and cannot
   inherit reduced-motion behavior cleanly.
3. Draw robots into the Plotly trace — rejected because it couples attention effects
   to chart recalculation and makes live and review activity harder to separate.

## Decision log

- Use the name **AikiBot Change Pulse**.
- Render in a dedicated overlay so live-edit indicators are not interrupted.
- Keep the overlay pointer-transparent and cancel stale pulses on every new selection.
- Trigger only after the visible Plotly snapshot has rendered.
- Use changed-file status already present in the active trace.
- Show every icon immediately, stagger its pop by 30 ms, and remove the overlay after 1.5 seconds.
- Debounce Review-mode resizing before replaying the pulse so the resize cannot cancel it.
- Group large or hidden change sets by visible top-level folders.
- Do not introduce any new Git, server, timer-polling, or API work.

## Large-repository correction

### Understanding

- History navigation can finish after the fixed two-frame pulse delay on large maps.
- Measuring every rendered tile delays the attention effect and adds layout work.
- Polling currently stats every tracked file, including files Git already reports as unchanged.
- Rapid navigation and the 2.5-second live-update cadence must remain unchanged.
- The fix must not add dependencies, API calls, or a new rendering architecture.

### Options considered

1. Await Plotly and narrow work to changed-file anchors — selected because it fixes
   the race and the repeated layout/filesystem work without changing product behavior.
2. Lazy-load commit traces — deferred because it changes the server and history data
   flow and is larger than the measured bottlenecks require.
3. Slow the polling interval — rejected because it would make live editing less useful.

### Decisions

- Await the active `Plotly.restyle` before scheduling a pulse.
- Ignore stale completions after rapid Older/Newer navigation.
- Scan slice metadata but call `getBoundingClientRect()` only for candidate anchors.
- Track signatures only for files Git marks changed and compare both old and new keys.
