"""Map hierarchy nodes to the parallel fields required by Plotly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True)
class VisualizationSnapshot:
    commit: CommitInfo
    nodes: list[HierarchyNode]


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
    )


def write_visualization(
    snapshots: Iterable[VisualizationSnapshot],
    output_path: Path,
) -> None:
    """Write commit snapshots to a self-contained interactive HTML file."""
    snapshot_list = list(snapshots)
    if not snapshot_list:
        raise ValueError("At least one commit snapshot is required")

    figure = go.Figure()
    for index, snapshot in enumerate(snapshot_list):
        figure.add_trace(_treemap_trace(snapshot, visible=index == 0))

    figure.update_layout(
        autosize=True,
        margin={"t": 8, "r": 8, "b": 8, "l": 8},
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
    output_path.write_text(
        _html_document(plot_html, snapshot_list),
        encoding="utf-8",
    )


def _treemap_trace(
    snapshot: VisualizationSnapshot,
    visible: bool,
) -> go.Treemap:
    data = to_treemap_data(snapshot.nodes)
    previous_path_details = [
        f"Previous path: {path}" if path else ""
        for path in data.previous_paths
    ]
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
            zip(data.paths, data.statuses, previous_path_details, strict=True)
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Path: %{customdata[0]}<br>"
            "Status: %{customdata[1]}<br>"
            "%{customdata[2]}"
            "<extra></extra>"
        ),
        textinfo="label",
        name=snapshot.commit.short_hash,
        visible=visible,
    )


def _html_document(
    plot_html: str,
    snapshots: list[VisualizationSnapshot],
) -> str:
    first = snapshots[0].commit
    commit_payload = json.dumps(
        [
            {
                "hash": snapshot.commit.short_hash,
                "message": snapshot.commit.message,
                "author": snapshot.commit.author,
                "date": _display_date(snapshot.commit.authored_at),
            }
            for snapshot in snapshots
        ]
    ).replace("</", "<\\/")

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
    .commit-nav {{ display: flex; gap: 12px; flex: 0 0 auto; }}
    .commit-nav button {{ min-height: 46px; padding: 0 22px; border: 1px solid #CBD5E1; border-radius: 10px; background: #FFFFFF; color: #172033; font-size: 16px; font-weight: 700; cursor: pointer; }}
    .commit-nav button:hover:not(:disabled) {{ border-color: #596FA8; background: #F1F5F9; }}
    .commit-nav button:disabled {{ cursor: not-allowed; opacity: .42; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px 30px; margin: 22px 0 18px; padding: 14px 16px; border: 1px solid #D8E0E9; border-radius: 12px; background: #FFFFFF; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 9px; color: #334155; font-size: 14px; white-space: nowrap; }}
    .legend-swatch {{ width: 18px; height: 18px; border: 1px solid #CBD5E1; border-radius: 4px; }}
    .chart-shell {{ height: calc(100vh - 252px); min-height: 480px; overflow: hidden; border: 1px solid #D8E0E9; border-radius: 12px; background: #FFFFFF; }}
    #aiki-map {{ width: 100%; height: 100%; }}
    @media (max-width: 760px) {{
      .page {{ padding: 20px 16px 16px; }}
      .header {{ align-items: stretch; flex-direction: column; }}
      .commit-nav {{ width: 100%; }}
      .commit-nav button {{ flex: 1; }}
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
        <div class="eyebrow">Commit <span id="commit-position">1 of {len(snapshots)}</span></div>
        <div class="commit-line"><code id="commit-hash">{escape(first.short_hash)}</code> — <strong id="commit-message">{escape(first.message)}</strong></div>
        <div class="commit-byline"><span id="commit-author">{escape(first.author)}</span> — <span id="commit-date">{escape(_display_date(first.authored_at))}</span></div>
      </div>
      <nav class="commit-nav" aria-label="Commit history">
        <button id="older-commit" type="button">← Older commit</button>
        <button id="newer-commit" type="button" disabled>Newer commit →</button>
      </nav>
    </header>
    <section class="legend" aria-label="Change status legend">
      {_legend_html()}
    </section>
    <section class="chart-shell">
      {plot_html}
    </section>
  </main>
  <script>
    const commits = {commit_payload};
    const graph = document.getElementById("aiki-map");
    const newerButton = document.getElementById("newer-commit");
    const olderButton = document.getElementById("older-commit");
    let currentCommit = 0;

    function showCommit(index) {{
      if (index < 0 || index >= commits.length) return;
      const visible = commits.map((_, traceIndex) => traceIndex === index);
      Plotly.restyle(graph, {{ visible }});
      currentCommit = index;
      const commit = commits[index];
      document.getElementById("commit-position").textContent = `${{index + 1}} of ${{commits.length}}`;
      document.getElementById("commit-hash").textContent = commit.hash;
      document.getElementById("commit-message").textContent = commit.message;
      document.getElementById("commit-author").textContent = commit.author;
      document.getElementById("commit-date").textContent = commit.date;
      newerButton.disabled = index === 0;
      olderButton.disabled = index === commits.length - 1;
      Plotly.Plots.resize(graph);
    }}

    newerButton.addEventListener("click", () => showCommit(currentCommit - 1));
    olderButton.addEventListener("click", () => showCommit(currentCommit + 1));
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
