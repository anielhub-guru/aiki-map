"""Map hierarchy nodes to the parallel fields required by Plotly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path
from typing import Iterable

import plotly.graph_objects as go

from git_reader import CommitInfo
from hierarchy import HierarchyNode


STATUS_COLORS = {
    "unchanged": "#E8EDF3",
    "changed": "#E9E4F2",
    "added": "#3A806F",
    "modified": "#C88732",
    "deleted": "#B4555D",
    "renamed": "#596FA8",
}

STATUS_LABELS = (
    ("unchanged", "Unchanged"),
    ("changed", "Contains changes"),
    ("added", "Added"),
    ("modified", "Modified"),
    ("deleted", "Deleted"),
    ("renamed", "Renamed"),
)

STATUS_TEXT_COLORS = {
    "unchanged": "#172033",
    "changed": "#172033",
    "added": "#FFFFFF",
    "modified": "#172033",
    "deleted": "#FFFFFF",
    "renamed": "#FFFFFF",
}


@dataclass(frozen=True)
class TreemapData:
    ids: list[str]
    labels: list[str]
    parents: list[str]
    values: list[int]
    colors: list[str]
    paths: list[str]
    statuses: list[str]
    previous_paths: list[str]
    details: list[str]


@dataclass(frozen=True)
class VisualizationSnapshot:
    commit: CommitInfo
    nodes: list[HierarchyNode]
    kind: str = "commit"
    change_count: int = 0


def to_treemap_data(nodes: Iterable[HierarchyNode]) -> TreemapData:
    """Return positionally aligned values for a Plotly treemap trace."""
    node_list = list(nodes)
    _validate_hierarchy(node_list)

    return TreemapData(
        ids=[node.node_id for node in node_list],
        labels=[node.label for node in node_list],
        parents=[node.parent_id for node in node_list],
        values=[node.value for node in node_list],
        colors=[STATUS_COLORS[node.status] for node in node_list],
        paths=[node.path or node.label for node in node_list],
        statuses=[node.status for node in node_list],
        previous_paths=[node.previous_path or "" for node in node_list],
        details=[node.detail for node in node_list],
    )


def write_visualization(
    snapshots: Iterable[VisualizationSnapshot],
    output_path: Path,
    live_updates: bool = False,
) -> None:
    """Write commit snapshots to a self-contained interactive HTML file."""
    output_path.write_text(
        render_visualization(snapshots, live_updates=live_updates),
        encoding="utf-8",
    )


def render_visualization(
    snapshots: Iterable[VisualizationSnapshot],
    live_updates: bool = False,
) -> str:
    """Return a self-contained visualization document."""
    snapshot_list = list(snapshots)
    if not snapshot_list:
        raise ValueError("At least one commit snapshot is required")

    figure = go.Figure()
    for index, snapshot in enumerate(snapshot_list):
        figure.add_trace(_treemap_trace(snapshot, visible=index == 0))

    figure.update_layout(
        autosize=True,
        margin={"t": 42, "r": 8, "b": 8, "l": 8},
        paper_bgcolor="#F8FAFC",
        font={"family": "Arial, sans-serif", "color": "#0F172A"},
        showlegend=False,
    )
    plot_html = figure.to_html(
        include_plotlyjs=True,
        full_html=False,
        div_id="aiki-map",
        config={"displaylogo": False, "responsive": True},
    )
    return _html_document(
        plot_html,
        snapshot_list,
        live_updates=live_updates,
        initial_version=visualization_version(snapshot_list),
    )


def visualization_payload(
    snapshots: Iterable[VisualizationSnapshot],
) -> dict[str, object]:
    """Return replacement traces and metadata for a live browser update."""
    snapshot_list = list(snapshots)
    return {
        "version": visualization_version(snapshot_list),
        "snapshots": _snapshot_payload(snapshot_list),
        "traces": [
            _treemap_trace(snapshot, visible=index == 0).to_plotly_json()
            for index, snapshot in enumerate(snapshot_list)
        ],
    }


def visualization_version(snapshots: Iterable[VisualizationSnapshot]) -> str:
    """Return a stable fingerprint for visually meaningful repository state."""
    snapshot_list = list(snapshots)
    working = snapshot_list[0]
    state = {
        "commits": [snapshot.commit.full_hash for snapshot in snapshot_list[1:]],
        "working": [
            (
                node.node_id,
                node.parent_id,
                node.status,
                node.previous_path,
                node.detail,
            )
            for node in working.nodes
        ],
    }
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _treemap_trace(
    snapshot: VisualizationSnapshot,
    visible: bool,
) -> go.Treemap:
    data = to_treemap_data(snapshot.nodes)
    previous_path_details = [
        f"Previous path: {path}" if path else ""
        for path in data.previous_paths
    ]
    change_details = [f"State: {detail}" if detail else "" for detail in data.details]
    return go.Treemap(
        ids=data.ids,
        labels=data.labels,
        parents=data.parents,
        values=data.values,
        branchvalues="total",
        marker={
            "colors": data.colors,
            "line": {"color": "#F8FAFC", "width": 2},
        },
        textfont={
            "color": [STATUS_TEXT_COLORS[status] for status in data.statuses]
        },
        pathbar={"visible": True, "thickness": 34, "textfont": {"size": 14}},
        customdata=list(
            zip(
                data.paths,
                data.statuses,
                previous_path_details,
                change_details,
                strict=True,
            )
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Path: %{customdata[0]}<br>"
            "Status: %{customdata[1]}<br>"
            "%{customdata[2]}<br>"
            "%{customdata[3]}"
            "<extra></extra>"
        ),
        textinfo="label",
        name=(
            "Working Changes"
            if snapshot.kind == "working"
            else snapshot.commit.short_hash
        ),
        visible=visible,
    )


def _html_document(
    plot_html: str,
    snapshots: list[VisualizationSnapshot],
    live_updates: bool,
    initial_version: str,
) -> str:
    payload = _snapshot_payload(snapshots)
    first = payload[0]
    snapshot_payload = json.dumps(payload).replace("</", "<\\/")
    live_updates_json = json.dumps(live_updates)
    version_json = json.dumps(initial_version)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aiki Map</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; background: #F8FAFC; color: #172033; }}
    body {{ font-family: Arial, sans-serif; }}
    .page {{ padding: 24px 32px 20px; }}
    .header {{ display: flex; justify-content: space-between; gap: 24px; align-items: end; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(28px, 3vw, 42px); line-height: 1.05; }}
    .eyebrow {{ margin-bottom: 6px; color: #64748B; font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }}
    .commit-line {{ font-size: 18px; line-height: 1.4; }}
    .commit-line code {{ font-size: 15px; }}
    .commit-byline {{ margin-top: 4px; color: #475569; font-size: 15px; }}
    .live-status {{ display: inline-block; margin-top: 6px; color: #9F3A44; font-size: 13px; font-weight: 700; }}
    .live-status[hidden] {{ display: none; }}
    .header-actions {{ display: flex; flex-direction: column; align-items: end; gap: 12px; flex: 0 0 auto; }}
    .view-switch, .commit-nav {{ display: flex; gap: 10px; }}
    .header-actions button {{ min-height: 46px; padding: 0 22px; border: 1px solid #CBD5E1; border-radius: 10px; background: #FFFFFF; color: #172033; font-size: 16px; font-weight: 700; cursor: pointer; }}
    .header-actions button:hover:not(:disabled):not(.active) {{ border-color: #596FA8; background: #F1F5F9; }}
    .header-actions button.active {{ border-color: #172033; background: #172033; color: #FFFFFF; }}
    .header-actions button:disabled {{ cursor: not-allowed; opacity: .42; }}
    .commit-nav[hidden] {{ display: none; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px 30px; margin: 22px 0 18px; padding: 14px 16px; border: 1px solid #D8E0E9; border-radius: 12px; background: #FFFFFF; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 9px; color: #334155; font-size: 14px; white-space: nowrap; }}
    .legend-swatch {{ width: 18px; height: 18px; border: 1px solid #CBD5E1; border-radius: 4px; }}
    .chart-shell {{ height: calc(100vh - 252px); min-height: 480px; overflow: hidden; border: 1px solid #D8E0E9; border-radius: 12px; background: #FFFFFF; }}
    #aiki-map {{ width: 100%; height: 100%; }}
    @media (max-width: 760px) {{
      .page {{ padding: 20px 16px 16px; }}
      .header {{ align-items: stretch; flex-direction: column; }}
      .header-actions {{ align-items: stretch; }}
      .view-switch, .commit-nav {{ width: 100%; }}
      .header-actions button {{ flex: 1; }}
      .legend {{ gap: 12px 20px; }}
      .chart-shell {{ height: calc(100vh - 340px); min-height: 420px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div>
        <h1>Aiki Map</h1>
        <div class="eyebrow" id="view-label">{escape(first["label"])}</div>
        <div class="commit-line"><code id="snapshot-key">{escape(first["key"])}</code> — <strong id="snapshot-message">{escape(first["message"])}</strong></div>
        <div class="commit-byline" id="snapshot-detail" hidden></div>
        <div class="live-status" id="live-status" role="status" hidden></div>
      </div>
      <div class="header-actions">
        <nav class="view-switch" aria-label="Visualization view">
          <button class="active" id="working-view" type="button">Working Changes</button>
          <button id="history-view" type="button">Commit History</button>
        </nav>
        <nav class="commit-nav" id="commit-nav" aria-label="Commit history" hidden>
          <button id="older-commit" type="button">← Older commit</button>
          <button id="newer-commit" type="button" disabled>Newer commit →</button>
        </nav>
      </div>
    </header>
    <section class="legend" aria-label="Change status legend">
      {_legend_html()}
    </section>
    <section class="chart-shell">
      {plot_html}
    </section>
  </main>
  <script>
    let snapshots = {snapshot_payload};
    const graph = document.getElementById("aiki-map");
    const workingButton = document.getElementById("working-view");
    const historyButton = document.getElementById("history-view");
    const commitNavigation = document.getElementById("commit-nav");
    const newerButton = document.getElementById("newer-commit");
    const olderButton = document.getElementById("older-commit");
    const liveStatus = document.getElementById("live-status");
    const liveUpdates = {live_updates_json};
    let stateVersion = {version_json};
    let historyStart = snapshots.findIndex(snapshot => snapshot.kind === "commit");
    let historyCount = snapshots.filter(snapshot => snapshot.kind === "commit").length;
    let currentHistoryIndex = 0;
    let refreshInProgress = false;

    function updateSnapshotMetadata(index) {{
      const snapshot = snapshots[index];
      document.getElementById("view-label").textContent = snapshot.label;
      document.getElementById("snapshot-key").textContent = snapshot.key;
      document.getElementById("snapshot-message").textContent = snapshot.message;
      const detail = document.getElementById("snapshot-detail");
      detail.textContent = snapshot.detail;
      detail.hidden = !snapshot.detail;
      const isWorking = snapshot.kind === "working";
      workingButton.classList.toggle("active", isWorking);
      historyButton.classList.toggle("active", !isWorking);
      commitNavigation.hidden = isWorking;
      if (!isWorking) {{
        currentHistoryIndex = snapshot.historyIndex;
        newerButton.disabled = currentHistoryIndex === 0;
        olderButton.disabled = currentHistoryIndex === historyCount - 1;
      }}
    }}

    function showSnapshot(index) {{
      if (index < 0 || index >= snapshots.length) return;
      const visible = snapshots.map((_, traceIndex) => traceIndex === index);
      Plotly.restyle(graph, {{ visible }});
      updateSnapshotMetadata(index);
      Plotly.Plots.resize(graph);
    }}

    async function refreshState() {{
      if (!liveUpdates || refreshInProgress) return;
      refreshInProgress = true;
      try {{
        const response = await fetch(`/api/state?version=${{encodeURIComponent(stateVersion)}}`, {{ cache: "no-store" }});
        if (response.status === 304) {{
          liveStatus.hidden = true;
          return;
        }}
        if (!response.ok) throw new Error(`Refresh failed (${{response.status}})`);

        const showingWorking = workingButton.classList.contains("active");
        const selectedCommit = showingWorking
          ? null
          : snapshots[historyStart + currentHistoryIndex]?.key;
        const payload = await response.json();
        snapshots = payload.snapshots;
        stateVersion = payload.version;
        historyStart = snapshots.findIndex(snapshot => snapshot.kind === "commit");
        historyCount = snapshots.filter(snapshot => snapshot.kind === "commit").length;

        let activeIndex = 0;
        if (!showingWorking) {{
          const matchingIndex = snapshots.findIndex(
            snapshot => snapshot.kind === "commit" && snapshot.key === selectedCommit
          );
          activeIndex = matchingIndex >= 0
            ? matchingIndex
            : historyStart + Math.min(currentHistoryIndex, historyCount - 1);
        }}
        payload.traces.forEach((trace, index) => {{
          trace.visible = index === activeIndex;
        }});
        await Plotly.react(graph, payload.traces, graph.layout);
        updateSnapshotMetadata(activeIndex);
        liveStatus.hidden = true;
      }} catch (error) {{
        liveStatus.textContent = "Live refresh unavailable — retrying";
        liveStatus.hidden = false;
      }} finally {{
        refreshInProgress = false;
      }}
    }}

    workingButton.addEventListener("click", () => showSnapshot(0));
    historyButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex));
    newerButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex - 1));
    olderButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex + 1));
    if (liveUpdates) window.setInterval(refreshState, 2500);
  </script>
</body>
</html>
"""


def _display_date(authored_at: str) -> str:
    try:
        value = datetime.fromisoformat(authored_at)
    except ValueError:
        return authored_at
    return f"{value.day} {value.strftime('%B %Y')}"


def _snapshot_payload(
    snapshots: list[VisualizationSnapshot],
) -> list[dict[str, object]]:
    history_count = sum(snapshot.kind == "commit" for snapshot in snapshots)
    history_index = 0
    payload = []

    for snapshot in snapshots:
        if snapshot.kind == "working":
            count = snapshot.change_count
            payload.append(
                {
                    "kind": "working",
                    "historyIndex": -1,
                    "label": "Working changes",
                    "key": "Working tree clean" if count == 0 else f"{count} file{'s' if count != 1 else ''}",
                    "message": (
                        f"No local changes since {snapshot.commit.short_hash}"
                        if count == 0
                        else f"changed since {snapshot.commit.short_hash}"
                    ),
                    "detail": "",
                }
            )
            continue

        payload.append(
            {
                "kind": "commit",
                "historyIndex": history_index,
                "label": f"Commit {history_index + 1} of {history_count}",
                "key": snapshot.commit.short_hash,
                "message": snapshot.commit.message,
                "detail": (
                    f"{snapshot.commit.author} — "
                    f"{_display_date(snapshot.commit.authored_at)}"
                ),
            }
        )
        history_index += 1

    return payload


def _legend_html() -> str:
    return "".join(
        (
            '<span class="legend-item">'
            f'<span class="legend-swatch" style="background:{STATUS_COLORS[status]}"></span>'
            f"{escape(label)}</span>"
        )
        for status, label in STATUS_LABELS
    )


def _validate_hierarchy(nodes: list[HierarchyNode]) -> None:
    if not nodes:
        raise ValueError("At least one hierarchy node is required")

    node_ids = {node.node_id for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("Hierarchy node IDs must be unique")

    for node in nodes:
        if node.status not in STATUS_COLORS:
            raise ValueError(f"Unsupported hierarchy status: {node.status}")
        if node.parent_id and node.parent_id not in node_ids:
            raise ValueError(
                f"Missing parent {node.parent_id!r} for node {node.node_id!r}"
            )
