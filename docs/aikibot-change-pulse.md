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
- A pulse should finish in approximately 1.2 seconds.
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
- Stagger icons by 45 ms, cap the stagger, and remove the overlay after 1.3 seconds.
- Group large or hidden change sets by visible top-level folders.
- Do not introduce any new Git, server, timer-polling, or API work.
