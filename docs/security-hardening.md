# Security hardening decisions

## Understanding

- AikiMap visualizes local Git repositories for IDE and terminal-agent users.
- Repository inspection must remain read-only and must not trust repository files.
- The live interface is local-only and may expose source diffs on demand.
- Detached IDE startup must continue without an external terminal.
- Existing native-window and browser-fallback workflows must keep working.
- Remote access, multi-user sessions, and repository mutation are out of scope.

## Assumptions

- One AikiMap process serves one repository through an ephemeral loopback port.
- The launch URL may carry an unguessable per-session token and must not send referrers.
- Diff previews may be truncated to protect application availability.
- Git metadata and repository configuration are treated as untrusted input.

## Decision log

- Execute the installed CLI by absolute file path for detached startup; do not resolve it through the inspected repository.
- Require the per-session token for the initial document and every API request.
- Reject unexpected HTTP `Host` values and add restrictive browser response headers.
- Bound Git patch output while the subprocess is running, before rendering truncation.
- Disable `core.fsmonitor` for every Git command issued by AikiMap.
- Preserve argument-array subprocess execution and existing path validation.
