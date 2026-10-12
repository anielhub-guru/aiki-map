---
name: aikimap
description: Open the AikiMap live repository view from a Codex IDE or desktop coding chat when the user asks to start, show, or launch AikiMap for the current local Git project.
---

# Open AikiMap

Find the local Git repository root for the current coding project. Run `aikimap ide --detach --repository <absolute-repository-root>` with the local command tool, then tell the user that the corner window is open. This command observes file changes while the agent continues working in the IDE; it does not start a second Codex session.

If `aikimap` is unavailable, explain that the user needs to install the local AikiMap package. Do not install software or start a terminal agent in its place.
