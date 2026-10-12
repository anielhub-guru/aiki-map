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

from git_reader import BranchInfo, CommitInfo
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
    kinds: list[str]


@dataclass(frozen=True)
class VisualizationSnapshot:
    commit: CommitInfo
    nodes: list[HierarchyNode]
    kind: str = "commit"
    change_count: int = 0
    activity_paths: tuple[str, ...] = ()
    activity_revision: int = 0
    branches: tuple[BranchInfo, ...] = ()
    history_ref: str = ""


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
        kinds=[node.kind for node in node_list],
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
        margin={"t": 32, "r": 6, "b": 6, "l": 6},
        paper_bgcolor="#FBFAF6",
        font={
            "family": "Avenir Next, Avenir, Segoe UI, sans-serif",
            "color": "#18211F",
        },
        showlegend=False,
        transition={"duration": 0},
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
        "branches": _branch_payload(snapshot_list[0].branches),
        "historyRef": snapshot_list[0].history_ref,
        "activity": {
            "paths": list(snapshot_list[0].activity_paths),
            "revision": snapshot_list[0].activity_revision,
        },
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
        "activity": [working.activity_revision, working.activity_paths],
        "branches": [(branch.ref, branch.tip, branch.current) for branch in working.branches],
        "historyRef": working.history_ref,
    }
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _treemap_trace(
    snapshot: VisualizationSnapshot,
    visible: bool,
) -> go.Treemap:
    data = to_treemap_data(snapshot.nodes)
    activity_paths = set(snapshot.activity_paths)
    active = [
        kind == "file" and path in activity_paths
        for path, kind in zip(data.paths, data.kinds, strict=True)
    ]
    previous_path_details = [
        f"Previous path: {path}" if path else ""
        for path in data.previous_paths
    ]
    change_details = [f"State: {detail}" if detail else "" for detail in data.details]
    return go.Treemap(
        ids=data.ids,
        labels=[f"● {label}" if editing else label for label, editing in zip(data.labels, active, strict=True)],
        parents=data.parents,
        values=data.values,
        branchvalues="total",
        marker={
            "colors": data.colors,
            "line": {
                "color": ["#F4C95D" if editing else "#F8FAFC" for editing in active],
                "width": [6 if editing else 2 for editing in active],
            },
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
                data.kinds,
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
    branches_json = json.dumps(_branch_payload(snapshots[0].branches)).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aiki Map</title>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{
      --canvas: #F1F0EA;
      --surface: #FBFAF6;
      --surface-raised: #FFFFFF;
      --ink: #18211F;
      --muted: #69736F;
      --line: #D9DDD8;
      --accent: #2E7566;
      --accent-soft: #DDEBE6;
      --danger: #A84E56;
      --shadow: 0 18px 42px rgba(35, 43, 40, .10);
    }}
    html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--canvas); color: var(--ink); }}
    body {{ font-family: "Avenir Next", Avenir, "Segoe UI", sans-serif; }}
    button {{ font: inherit; }}
    .page {{ display: grid; grid-template-areas: "header" "activity" "map" "legend"; grid-template-rows: auto auto minmax(0, 1fr) auto; gap: 12px; height: 100vh; padding: 16px; }}
    .header {{ grid-area: header; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 20px; align-items: start; }}
    .window-drag-region {{ min-width: 0; cursor: grab; user-select: none; }}
    .window-drag-region:active {{ cursor: grabbing; }}
    .brand-row {{ display: flex; align-items: center; gap: 9px; margin-bottom: 8px; }}
    .branch-bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin-bottom: 7px; font-size: 11px; color: var(--muted); cursor: default; }}
    .branch-name {{ color: var(--accent); font-weight: 750; }}
    .branch-bar label {{ display: inline-flex; align-items: center; gap: 5px; }}
    .branch-bar label[hidden] {{ display: none; }}
    .branch-bar select {{ max-width: 200px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }}
    .brand-signal {{ width: 9px; height: 9px; border-radius: 999px; background: var(--accent); box-shadow: 0 0 0 5px var(--accent-soft); }}
    h1 {{ margin: 0; font-size: 22px; font-weight: 680; letter-spacing: -.035em; line-height: 1; }}
    .session-indicator {{ padding: 4px 8px; border: 1px solid #C8DDD5; border-radius: 999px; background: var(--accent-soft); color: #245C51; font-size: 11px; font-weight: 700; letter-spacing: .02em; white-space: nowrap; }}
    .session-indicator[data-phase="stopped"] {{ border-color: #DDD6CB; background: #EEEAE2; color: #665F55; }}
    .session-indicator[data-phase="dismissed"] {{ border-color: #E4CDD0; background: #F3E2E4; color: #843D44; }}
    .directory-activity {{ max-width: 200px; overflow: hidden; padding: 4px 8px; border: 1px solid #E2BD58; border-radius: 999px; background: #FFF4C7; color: #60470A; font-size: 11px; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }}
    .directory-activity[hidden] {{ display: none; }}
    .eyebrow {{ margin-bottom: 3px; color: var(--muted); font-size: 10px; font-weight: 750; letter-spacing: .11em; text-transform: uppercase; }}
    .commit-line {{ display: flex; align-items: baseline; gap: 6px; min-width: 0; font-size: 14px; line-height: 1.35; }}
    .commit-line code {{ flex: 0 0 auto; font: 700 12px/1.3 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .commit-line strong {{ overflow: hidden; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }}
    .commit-byline {{ margin-top: 3px; color: var(--muted); font-size: 12px; }}
    .live-status {{ display: inline-block; margin-top: 4px; color: var(--danger); font-size: 11px; font-weight: 700; }}
    .live-status[hidden] {{ display: none; }}
    .activity-status {{ grid-area: activity; display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; align-items: center; gap: 8px; width: 100%; min-height: 42px; padding: 6px 12px 6px 8px; border: 1px solid #E2BD58; border-radius: 12px; background: #FFF4C7; color: #60470A; font-size: 10px; font-weight: 750; text-align: left; box-shadow: 0 5px 16px rgba(96, 71, 10, .12); cursor: pointer; }}
    .activity-status[hidden] {{ display: none; }}
    .activity-pulse {{ width: 8px; height: 8px; border-radius: 999px; background: #D99B16; animation: editing-pulse 1.15s ease-out infinite; }}
    .activity-status strong {{ overflow: hidden; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }}
    .activity-action {{ color: #7A5B0A; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }}
    .activity-status:hover {{ border-color: #D6A72B; background: #FFF0AD; }}
    .activity-status:focus-visible {{ outline: 3px solid rgba(46, 117, 102, .28); outline-offset: 2px; }}
    @keyframes editing-pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(217, 155, 22, .55); }} 75%, 100% {{ box-shadow: 0 0 0 7px rgba(217, 155, 22, 0); }} }}
    @media (prefers-reduced-motion: reduce) {{ .activity-pulse {{ animation: none; }} }}
    .header-stack {{ display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }}
    .session-controls-slot:empty {{ display: none; }}
    .session-toolbar {{ display: flex; align-items: center; gap: 3px; padding: 3px; border: 1px solid #D4D8D3; border-radius: 10px; background: rgba(255, 255, 255, .86); box-shadow: 0 8px 24px rgba(36, 45, 41, .09); backdrop-filter: blur(14px); }}
    .session-toolbar button {{ min-height: 30px; padding: 0 10px; border: 0; border-radius: 7px; background: transparent; color: #3F4945; font-size: 11px; font-weight: 700; cursor: pointer; }}
    .session-toolbar button:hover {{ background: #ECEEEA; color: var(--ink); }}
    .session-toolbar .end-session {{ color: #913E47; }}
    .header-actions {{ display: flex; flex-direction: column; align-items: end; gap: 7px; flex: 0 0 auto; }}
    .view-switch, .commit-nav {{ display: flex; gap: 5px; }}
    .header-actions button {{ min-height: 34px; padding: 0 13px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface-raised); color: #46514D; font-size: 12px; font-weight: 700; cursor: pointer; }}
    .header-actions button:hover:not(:disabled):not(.active) {{ border-color: #91A89F; background: #F4F6F3; }}
    .header-actions button.active {{ border-color: var(--ink); background: var(--ink); color: #FFFFFF; }}
    .header-actions button:disabled {{ cursor: not-allowed; opacity: .42; }}
    .commit-nav[hidden] {{ display: none; }}
    .legend {{ grid-area: legend; display: flex; flex-wrap: wrap; gap: 7px 16px; padding: 8px 11px; border: 1px solid var(--line); border-radius: 10px; background: rgba(255, 255, 255, .68); }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; color: #56615D; font-size: 11px; white-space: nowrap; }}
    .legend-swatch {{ width: 10px; height: 10px; border: 1px solid rgba(24, 33, 31, .14); border-radius: 3px; }}
    .chart-shell {{ grid-area: map; position: relative; min-height: 0; overflow: hidden; border: 1px solid var(--line); border-radius: 14px; background: var(--surface); box-shadow: var(--shadow); }}
    #aiki-map {{ width: 100%; height: 100%; }}
    .activity-robots {{ position: absolute; inset: 0; z-index: 10; overflow: hidden; pointer-events: none; }}
    .activity-robot {{ position: absolute; display: grid; place-items: center; width: 56px; height: 56px; border: 3px solid #FFFFFF; border-radius: 18px; background: #DDF5ED; box-shadow: 0 5px 18px rgba(19, 79, 71, .4); transform: translate(-50%, -50%); animation: robot-bob 1.25s ease-in-out infinite; }}
    .activity-robot[data-fallback="true"] {{ border-color: #FFF4C7; box-shadow: 0 0 0 3px #D99B16, 0 5px 18px rgba(19, 79, 71, .4); }}
    .activity-robot svg {{ width: 46px; height: 46px; overflow: visible; }}
    .activity-robot .robot-eyes {{ animation: robot-blink 3.2s ease-in-out infinite; transform-origin: center; }}
    @keyframes robot-bob {{ 0%, 100% {{ translate: 0 0; }} 50% {{ translate: 0 -3px; }} }}
    @keyframes robot-blink {{ 0%, 44%, 52%, 100% {{ transform: scaleY(1); }} 48% {{ transform: scaleY(.15); }} }}
    @media (prefers-reduced-motion: reduce) {{ .activity-robot, .activity-robot .robot-eyes {{ animation: none; }} }}
    /*
      Legacy fixed sidebar retained for a possible design reversal.
      .file-panel {{ position: fixed; z-index: 20; top: 20px; right: 20px; width: min(460px, calc(100vw - 40px)); max-height: calc(100vh - 40px); overflow: auto; padding: 22px; border: 1px solid #CBD5E1; border-radius: 14px; background: #FFFFFF; box-shadow: 0 18px 48px rgba(15, 23, 42, .22); }}
      .file-panel[hidden] {{ display: none; }}
      .file-panel-header {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; }}
      .file-panel h2 {{ margin: 0; font-size: 22px; overflow-wrap: anywhere; }}
      .file-panel-path {{ display: block; margin: 7px 0 18px; color: #475569; overflow-wrap: anywhere; }}
      .file-panel-close {{ flex: 0 0 auto; width: 36px; height: 36px; border: 1px solid #CBD5E1; border-radius: 8px; background: #FFFFFF; color: #172033; font-size: 22px; cursor: pointer; }}
    */
    .file-inspector {{ position: absolute; z-index: 20; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; padding: clamp(18px, 3vw, 42px); color: #172033; }}
    .file-inspector[hidden] {{ display: none; }}
    .file-inspector[data-status="unchanged"] {{ background: #E8EDF3; }}
    .file-inspector[data-status="changed"] {{ background: #E9E4F2; }}
    .file-inspector[data-status="added"] {{ background: #3A806F; color: #FFFFFF; }}
    .file-inspector[data-status="modified"] {{ background: #C88732; }}
    .file-inspector[data-status="deleted"] {{ background: #B4555D; color: #FFFFFF; }}
    .file-inspector[data-status="renamed"] {{ background: #596FA8; color: #FFFFFF; }}
    .file-inspector-toolbar {{ position: sticky; z-index: 2; top: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: calc(clamp(18px, 3vw, 42px) * -1) calc(clamp(18px, 3vw, 42px) * -1) 18px; padding: 12px clamp(18px, 3vw, 42px); background: rgba(255, 255, 255, .88); color: #172033; box-shadow: 0 1px 0 rgba(23, 32, 51, .12); backdrop-filter: blur(14px); }}
    .file-inspector-back {{ min-height: 36px; padding: 0 13px; border: 1px solid rgba(23, 32, 51, .24); border-radius: 9px; background: #FFFFFF; color: #172033; font-weight: 750; cursor: pointer; }}
    .file-inspector-back:hover {{ border-color: var(--accent); color: var(--accent); }}
    .file-inspector-hint {{ color: #5D6664; font-size: 11px; }}
    .file-inspector-header {{ display: block; }}
    .file-inspector h2 {{ margin: 0; font-size: clamp(17px, 1.7vw, 22px); overflow-wrap: anywhere; }}
    .file-inspector-path {{ display: block; margin: 5px 0 14px; color: inherit; opacity: .78; overflow-wrap: anywhere; }}
    .file-inspector-body {{ flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }}
    .file-facts {{ display: grid; grid-template-columns: max-content 1fr; gap: 7px 14px; margin: 0 0 16px; }}
    .file-facts dt {{ color: inherit; font-weight: 700; opacity: .72; }}
    .file-facts dd {{ margin: 0; overflow-wrap: anywhere; }}
    .show-diff {{ width: 100%; min-height: 44px; border: 1px solid currentColor; border-radius: 9px; background: #172033; color: #FFFFFF; font-size: 15px; font-weight: 700; cursor: pointer; }}
    .show-diff:disabled {{ cursor: wait; opacity: .62; }}
    .diff-output h3 {{ margin: 22px 0 8px; font-size: 14px; }}
    .diff-patch {{ overflow: auto; padding: 8px 0; border-radius: 9px; background: #111827; color: #D1D5DB; font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    .diff-line {{ min-width: max-content; padding: 0 14px 0 11px; border-left: 3px solid transparent; white-space: pre; }}
    .diff-line.added {{ border-left-color: #4ADE80; background: rgba(34, 197, 94, .17); color: #BBF7D0; }}
    .diff-line.deleted {{ border-left-color: #FB7185; background: rgba(244, 63, 94, .17); color: #FECDD3; }}
    .diff-line.hunk {{ background: rgba(96, 165, 250, .10); color: #93C5FD; }}
    .diff-line.metadata {{ color: #94A3B8; }}
    .diff-note {{ margin: 14px 0 0; color: #64748B; font-size: 13px; }}
    .file-inspector.compact {{ padding: 12px; }}
    .file-inspector.compact .file-inspector-toolbar {{ margin: -12px -12px 12px; padding: 8px 12px; }}
    .file-inspector.compact .file-inspector-path {{ margin-bottom: 9px; font-size: 12px; }}
    .file-inspector.compact .file-facts {{ gap: 4px 9px; margin-bottom: 10px; font-size: 12px; }}
    .file-inspector.compact .show-diff {{ min-height: 36px; }}
    .file-inspector.cramped .file-inspector-path,
    .file-inspector.cramped .file-facts dt:nth-of-type(2),
    .file-inspector.cramped #file-comparison {{ display: none; }}
    body.ambient-mode .page {{ grid-template-rows: auto auto minmax(0, 1fr) auto; gap: 9px; padding: 10px; }}
    body.ambient-mode .header {{ grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }}
    body.ambient-mode .brand-row {{ margin-bottom: 5px; }}
    body.ambient-mode h1 {{ font-size: 16px; }}
    body.ambient-mode .brand-signal {{ width: 7px; height: 7px; box-shadow: 0 0 0 4px var(--accent-soft); }}
    body.ambient-mode .session-indicator {{ padding: 3px 6px; font-size: 9px; }}
    body.ambient-mode .eyebrow {{ display: none; }}
    body.ambient-mode .commit-line {{ font-size: 11px; }}
    body.ambient-mode .commit-line code {{ font-size: 10px; }}
    body.ambient-mode .activity-status {{ min-height: 36px; padding-block: 3px; }}
    body.ambient-mode .commit-byline,
    body.ambient-mode .header-actions {{ display: none; }}
    body.ambient-mode .legend {{ gap: 4px 8px; padding: 5px 7px; }}
    body.ambient-mode .legend-item {{ gap: 4px; font-size: 9px; }}
    body.ambient-mode .legend-swatch {{ width: 9px; height: 9px; }}
    body.ambient-mode .header-stack {{ justify-content: flex-start; }}
    body.ambient-mode .session-toolbar {{ border-color: transparent; background: transparent; box-shadow: none; backdrop-filter: none; }}
    body.ambient-mode .session-toolbar button {{ min-height: 26px; padding: 0 7px; font-size: 10px; }}
    body.ambient-mode .chart-shell {{ border-radius: 11px; box-shadow: 0 10px 28px rgba(35, 43, 40, .08); }}
    @media (max-width: 760px) {{
      .page {{ padding: 12px; }}
      .header {{ grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }}
      .header-actions {{ align-items: flex-end; }}
      .legend {{ gap: 7px 12px; }}
    }}
    @media (max-width: 520px), (max-height: 560px) {{
      .page {{ gap: 8px; padding: 10px; }}
      .branch-bar {{ margin-bottom: 4px; }}
      .branch-bar label {{ min-width: 0; }}
      .branch-bar select {{ max-width: min(220px, 48vw); }}
      .directory-activity {{ display: none; }}
      .activity-status {{ min-height: 36px; border-radius: 10px; }}
      .activity-action {{ display: none; }}
      .legend {{ gap: 4px 8px; padding: 5px 7px; }}
      .legend-item {{ gap: 4px; font-size: 9px; }}
      .legend-swatch {{ width: 9px; height: 9px; }}
      .activity-robot {{ width: 48px; height: 48px; border-radius: 15px; }}
      .activity-robot svg {{ width: 39px; height: 39px; }}
      .file-inspector-hint {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div class="window-drag-region" title="Drag the brand row to move AikiMap">
        <div class="brand-row pywebview-drag-region">
          <span class="brand-signal" aria-hidden="true"></span>
          <h1>AikiMap</h1>
          <span class="session-indicator" id="session-indicator" data-phase="active">Live</span>
          <span class="directory-activity" id="directory-activity" role="status" hidden></span>
        </div>
        <div class="branch-bar">
          <span class="branch-name" id="branch-name"></span>
          <label id="history-branch-control">History branch <select id="branch-picker" aria-label="History branch"></select></label>
        </div>
        <div class="eyebrow" id="view-label">{escape(first["label"])}</div>
        <div class="commit-line"><code id="snapshot-key">{escape(first["key"])}</code> — <strong id="snapshot-message">{escape(first["message"])}</strong></div>
        <div class="commit-byline" id="snapshot-detail" hidden></div>
        <div class="live-status" id="live-status" role="status" hidden></div>
      </div>
      <div class="header-stack">
        <div class="session-controls-slot" id="aikimap-session-controls-slot"></div>
        <div class="header-actions">
          <nav class="view-switch" aria-label="Visualization view">
            <button class="active" id="working-view" type="button">Working</button>
            <button id="history-view" type="button">History</button>
          </nav>
          <nav class="commit-nav" id="commit-nav" aria-label="Commit history" hidden>
            <button id="older-commit" type="button">← Older</button>
            <button id="newer-commit" type="button" disabled>Newer →</button>
          </nav>
        </div>
      </div>
    </header>
    <button class="activity-status" id="activity-status" type="button" aria-label="Open the file currently being edited" hidden>
      <span class="activity-pulse" aria-hidden="true"></span>
      <span>EDITING</span>
      <strong id="activity-file"></strong>
      <span class="activity-action">View file →</span>
    </button>
    <section class="chart-shell">
      {plot_html}
      <div class="activity-robots" id="activity-robots" aria-hidden="true"></div>
      <aside class="file-inspector" id="file-inspector" aria-labelledby="file-inspector-title" hidden>
        <div class="file-inspector-toolbar">
          <button class="file-inspector-back" id="file-inspector-back" type="button">← Back to map</button>
          <span class="file-inspector-hint">Esc also returns</span>
        </div>
        <div class="file-inspector-header">
          <h2 id="file-inspector-title"></h2>
        </div>
        <code class="file-inspector-path" id="file-inspector-path"></code>
        <div class="file-inspector-body">
          <dl class="file-facts">
            <dt>State</dt><dd id="file-state"></dd>
            <dt>Compared</dt><dd id="file-comparison"></dd>
            <dt>Changes</dt><dd id="file-line-counts"></dd>
            <dt id="previous-path-label" hidden>Previous path</dt><dd id="file-previous-path" hidden></dd>
          </dl>
          <button class="show-diff" id="show-diff" type="button">Show Diff</button>
          <div class="diff-output" id="diff-output" aria-live="polite"></div>
          <p class="diff-note" id="diff-note" hidden></p>
        </div>
      </aside>
    </section>
    <section class="legend" aria-label="Change status legend">
      {_legend_html()}
    </section>
  </main>
  <!--
    Legacy fixed sidebar markup retained for a possible design reversal.
    <aside class="file-panel" id="file-panel" aria-labelledby="file-panel-title" hidden>
      <div class="file-panel-header">
        <h2 id="file-panel-title"></h2>
        <button class="file-panel-close" id="file-panel-close" type="button" aria-label="Close file details">×</button>
      </div>
      <code class="file-panel-path" id="file-panel-path"></code>
      <dl class="file-facts">
        <dt>State</dt><dd id="file-state"></dd>
        <dt>Compared</dt><dd id="file-comparison"></dd>
        <dt>Changes</dt><dd id="file-line-counts"></dd>
        <dt id="previous-path-label" hidden>Previous path</dt><dd id="file-previous-path" hidden></dd>
      </dl>
      <button class="show-diff" id="show-diff" type="button">Show Diff</button>
      <div class="diff-output" id="diff-output" aria-live="polite"></div>
      <p class="diff-note" id="diff-note" hidden></p>
    </aside>
  -->
  <script>
    let snapshots = {snapshot_payload};
    const graph = document.getElementById("aiki-map");
    const workingButton = document.getElementById("working-view");
    const historyButton = document.getElementById("history-view");
    const commitNavigation = document.getElementById("commit-nav");
    const newerButton = document.getElementById("newer-commit");
    const olderButton = document.getElementById("older-commit");
    const liveStatus = document.getElementById("live-status");
    const activityStatus = document.getElementById("activity-status");
    const activityFile = document.getElementById("activity-file");
    const directoryActivity = document.getElementById("directory-activity");
    const sessionIndicator = document.getElementById("session-indicator");
    const branchName = document.getElementById("branch-name");
    const branchControl = document.getElementById("history-branch-control");
    const branchPicker = document.getElementById("branch-picker");
    const chartShell = document.querySelector(".chart-shell");
    const activityRobots = document.getElementById("activity-robots");
    const fileInspector = document.getElementById("file-inspector");
    const fileInspectorBack = document.getElementById("file-inspector-back");
    const showDiffButton = document.getElementById("show-diff");
    const diffOutput = document.getElementById("diff-output");
    const diffNote = document.getElementById("diff-note");
    const liveUpdates = {live_updates_json};
    const sessionToken = new URLSearchParams(window.location.search).get("token") ?? "";
    let stateVersion = {version_json};
    let historyStart = snapshots.findIndex(snapshot => snapshot.kind === "commit");
    let historyCount = snapshots.filter(snapshot => snapshot.kind === "commit").length;
    let currentHistoryIndex = 0;
    let currentSnapshotIndex = 0;
    let refreshInProgress = false;
    let selectedFile = null;
    let activityTimer = null;
    let activePaths = [];
    let historyRef = "";
    let filePanelHistoryActive = false;

    function apiFetch(resource, options = {{}}) {{
      const headers = new Headers(options.headers ?? {{}});
      headers.set("X-AikiMap-Token", sessionToken);
      return fetch(resource, {{ ...options, headers }});
    }}

    function updateBranchControls(branches, selectedRef) {{
      const current = branches.find(branch => branch.current);
      const selectableBranches = branches.filter(branch => branch.selectable);
      branchName.textContent = `⑂ ${{current?.name ?? "Detached HEAD"}}`;
      branchName.title = "Checked-out branch (Working view)";
      branchControl.hidden = selectableBranches.length === 0;
      branchPicker.replaceChildren(new Option(current ? `${{current.name}} · current` : "Detached HEAD", ""));
      for (const remote of [false, true]) {{
        const group = document.createElement("optgroup");
        group.label = remote ? "Remote branches" : "Local branches";
        for (const branch of selectableBranches.filter(branch => branch.remote === remote)) {{
          group.append(new Option(branch.name, branch.ref));
        }}
        if (group.children.length) branchPicker.append(group);
      }}
      historyRef = selectableBranches.some(branch => branch.ref === selectedRef) ? selectedRef : "";
      branchPicker.value = historyRef;
      branchPicker.disabled = !liveUpdates;
    }}
    updateBranchControls({branches_json}, "");

    function positionActivityRobots() {{
      activityRobots.replaceChildren();
      if (currentSnapshotIndex !== 0 || !activePaths.length) return;
      const shellBounds = chartShell.getBoundingClientRect();
      const visibleTiles = new Map();
      for (const slice of graph.querySelectorAll("g.slice")) {{
        const datum = slice.__data__;
        const id = datum?.id ?? datum?.data?.id;
        if (!id) continue;
        const tile = slice.querySelector("rect, path.surface") ?? slice;
        const bounds = tile.getBoundingClientRect();
        if (!bounds.width || !bounds.height) continue;
        visibleTiles.set(id, bounds);
      }}
      const groupedAnchors = new Map();
      for (const path of activePaths) {{
        const parts = path.split("/");
        const candidates = [`file:${{path}}`];
        parts.pop();
        while (parts.length) {{
          candidates.push(`dir:${{parts.join("/")}}`);
          parts.pop();
        }}
        candidates.push("repo:/");
        const anchorId = candidates.find(candidate => visibleTiles.has(candidate));
        if (!anchorId) continue;
        const anchoredPaths = groupedAnchors.get(anchorId) ?? [];
        anchoredPaths.push(path);
        groupedAnchors.set(anchorId, anchoredPaths);
      }}
      for (const [anchorId, paths] of groupedAnchors) {{
        const bounds = visibleTiles.get(anchorId);
        const robot = document.createElement("span");
        robot.className = "activity-robot";
        robot.dataset.anchor = anchorId;
        robot.dataset.fallback = String(!anchorId.startsWith("file:"));
        robot.title = `${{paths.join("\\n")}}${{paths.length === 1 ? " is" : " are"}} being edited`;
        robot.style.left = `${{Math.max(30, Math.min(shellBounds.width - 30, bounds.left - shellBounds.left + bounds.width / 2))}}px`;
        robot.style.top = `${{Math.max(30, Math.min(shellBounds.height - 30, bounds.top - shellBounds.top + bounds.height / 2))}}px`;
        robot.innerHTML = `<svg viewBox="0 0 32 32" role="presentation" aria-hidden="true">
          <path d="M16 4v4" stroke="#23675D" stroke-width="2.3" stroke-linecap="round"/>
          <circle cx="16" cy="3.5" r="2" fill="#E5A729"/>
          <rect x="3" y="8" width="26" height="20" rx="8" fill="#287D70"/>
          <rect x="6" y="11" width="20" height="14" rx="5" fill="#F6FFFA"/>
          <g class="robot-eyes" fill="#23675D"><circle cx="12" cy="17" r="2"/><circle cx="20" cy="17" r="2"/></g>
          <path d="M12 21c2 2 6 2 8 0" stroke="#D88F27" stroke-width="1.8" fill="none" stroke-linecap="round"/>
        </svg>`;
        activityRobots.append(robot);
      }}
    }}

    window.aikimapSetDisplayMode = mode => {{
      document.body.classList.toggle("ambient-mode", mode === "ambient");
      const compact = mode === "ambient";
      Plotly.relayout(graph, compact
        ? {{ "margin.t": 24, "margin.r": 3, "margin.b": 3, "margin.l": 3 }}
        : {{ "margin.t": 32, "margin.r": 6, "margin.b": 6, "margin.l": 6 }}
      );
      window.requestAnimationFrame(() => Plotly.Plots.resize(graph));
    }};

    async function refreshSessionStatus() {{
      if (!liveUpdates) return;
      try {{
        const response = await apiFetch("/api/session", {{ cache: "no-store" }});
        if (!response.ok) return;
        const session = await response.json();
        const source = session.source
          ? session.source.replaceAll("-", " ")
          : "Repository";
        const phase = session.phase === "manual" ? "view" : session.phase;
        sessionIndicator.dataset.phase = phase;
        sessionIndicator.textContent = `${{source}} · ${{phase}}`;
      }} catch (error) {{
        sessionIndicator.textContent = "Local view";
      }}
    }}

    function updateSnapshotMetadata(index) {{
      currentSnapshotIndex = index;
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
      closeFilePanel();
      const visible = snapshots.map((_, traceIndex) => traceIndex === index);
      Plotly.restyle(graph, {{ visible }});
      updateSnapshotMetadata(index);
      Plotly.Plots.resize(graph);
      window.requestAnimationFrame(positionActivityRobots);
    }}

    function updateActivity(activity) {{
      window.clearTimeout(activityTimer);
      activePaths = activity?.paths ?? [];
      window.requestAnimationFrame(positionActivityRobots);
      if (!activity?.paths?.length) {{
        activityStatus.hidden = true;
        directoryActivity.hidden = true;
        return;
      }}
      const directories = [...new Set(activePaths.map(path => path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "repository root"))];
      directoryActivity.textContent = `Working in ${{directories[0]}}${{directories.length > 1 ? ` +${{directories.length - 1}}` : ""}}`;
      directoryActivity.title = directories.join("\\n");
      directoryActivity.hidden = false;
      const names = activity.paths.map(path => path.split("/").pop());
      activityFile.textContent = names.length === 1
        ? names[0]
        : `${{names[0]}} +${{names.length - 1}}`;
      activityFile.title = activity.paths.join("\\n");
      activityStatus.hidden = false;
      activityTimer = window.setTimeout(() => {{
        activityStatus.hidden = true;
        directoryActivity.hidden = true;
        activePaths = [];
        positionActivityRobots();
      }}, 6500);
    }}

    async function refreshState(selectBranchTip = false) {{
      if (!liveUpdates || refreshInProgress) return;
      refreshInProgress = true;
      branchPicker.disabled = true;
      try {{
        const response = await apiFetch(`/api/state?version=${{encodeURIComponent(stateVersion)}}&branch=${{encodeURIComponent(historyRef)}}`, {{ cache: "no-store" }});
        if (response.status === 304) {{
          liveStatus.hidden = true;
          return;
        }}
        if (!response.ok) throw new Error(`Refresh failed (${{response.status}})`);

        const showingWorking = !selectBranchTip && workingButton.classList.contains("active");
        const selectedCommit = showingWorking || selectBranchTip
          ? null
          : snapshots[historyStart + currentHistoryIndex]?.key;
        const payload = await response.json();
        updateActivity(payload.activity);
        snapshots = payload.snapshots;
        updateBranchControls(payload.branches, payload.historyRef);
        stateVersion = payload.version;
        historyStart = snapshots.findIndex(snapshot => snapshot.kind === "commit");
        historyCount = snapshots.filter(snapshot => snapshot.kind === "commit").length;

        let activeIndex = 0;
        if (!showingWorking) {{
          const matchingIndex = snapshots.findIndex(
            snapshot => snapshot.kind === "commit" && snapshot.key === selectedCommit
          );
          activeIndex = selectBranchTip ? historyStart : matchingIndex >= 0
            ? matchingIndex
            : historyStart + Math.min(currentHistoryIndex, historyCount - 1);
        }}
        payload.traces.forEach((trace, index) => {{
          trace.visible = index === activeIndex;
        }});
        await Plotly.react(graph, payload.traces, graph.layout);
        closeFilePanel();
        updateSnapshotMetadata(activeIndex);
        window.requestAnimationFrame(positionActivityRobots);
        liveStatus.hidden = true;
      }} catch (error) {{
        liveStatus.textContent = "Live refresh unavailable — retrying";
        liveStatus.hidden = false;
      }} finally {{
        refreshInProgress = false;
        branchPicker.disabled = !liveUpdates;
      }}
    }}

    function closeFilePanel() {{
      if (filePanelHistoryActive) {{
        window.history.back();
        return;
      }}
      hideFilePanel();
    }}

    function hideFilePanel() {{
      fileInspector.hidden = true;
      selectedFile = null;
      filePanelHistoryActive = false;
      diffOutput.replaceChildren();
      diffNote.hidden = true;
    }}

    function positionFileInspector() {{
      const graphBounds = graph.getBoundingClientRect();
      const shellBounds = chartShell.getBoundingClientRect();
      const plotSize = graph._fullLayout?._size;
      const left = plotSize?.l ?? 8;
      const top = plotSize?.t ?? 42;
      const width = plotSize?.w ?? graphBounds.width - 16;
      const height = plotSize?.h ?? graphBounds.height - 50;
      if (width < 80 || height < 70) return false;
      fileInspector.style.left = `${{graphBounds.left - shellBounds.left + left}}px`;
      fileInspector.style.top = `${{graphBounds.top - shellBounds.top + top}}px`;
      fileInspector.style.width = `${{width}}px`;
      fileInspector.style.height = `${{height}}px`;
      fileInspector.classList.toggle("compact", width < 520 || height < 340);
      fileInspector.classList.toggle("cramped", width < 320 || height < 220);
      return true;
    }}

    function fileRequest(path, snapshot, includeDiff) {{
      const parameters = new URLSearchParams({{
        path,
        kind: snapshot.kind,
        revision: snapshot.revision,
        diff: includeDiff ? "1" : "0",
        branch: historyRef,
      }});
      return apiFetch(`/api/file?${{parameters}}`, {{ cache: "no-store" }});
    }}

    async function openFilePanel(path, status) {{
      if (!liveUpdates || !positionFileInspector()) return;
      if (fileInspector.hidden) {{
        window.history.pushState({{ aikimapFile: true }}, "", window.location.href);
        filePanelHistoryActive = true;
      }}
      const snapshot = snapshots[currentSnapshotIndex];
      selectedFile = {{ path, snapshot }};
      fileInspector.dataset.status = status;
      fileInspector.hidden = false;
      document.getElementById("file-inspector-title").textContent = path.split("/").pop();
      document.getElementById("file-inspector-path").textContent = path;
      document.getElementById("file-state").textContent = "Loading…";
      document.getElementById("file-comparison").textContent = "";
      document.getElementById("file-line-counts").textContent = "";
      document.getElementById("previous-path-label").hidden = true;
      document.getElementById("file-previous-path").hidden = true;
      showDiffButton.disabled = true;
      showDiffButton.hidden = false;
      diffOutput.replaceChildren();
      diffNote.hidden = true;

      try {{
        const response = await fileRequest(path, snapshot, false);
        if (!response.ok) throw new Error(`File details failed (${{response.status}})`);
        const details = await response.json();
        if (!selectedFile || selectedFile.path !== path) return;
        document.getElementById("file-state").textContent = details.state;
        document.getElementById("file-comparison").textContent = details.comparison;
        document.getElementById("file-line-counts").textContent = details.binary
          ? "Binary file"
          : `+${{details.additions}} / −${{details.deletions}} lines`;
        if (details.previousPath) {{
          document.getElementById("previous-path-label").hidden = false;
          const previousPath = document.getElementById("file-previous-path");
          previousPath.textContent = details.previousPath;
          previousPath.hidden = false;
        }}
        showDiffButton.disabled = false;
      }} catch (error) {{
        document.getElementById("file-state").textContent = "Details unavailable";
        diffNote.textContent = "Could not read this file’s Git details.";
        diffNote.hidden = false;
      }}
    }}

    async function showSelectedDiff() {{
      if (!selectedFile) return;
      showDiffButton.disabled = true;
      showDiffButton.textContent = "Loading Diff…";
      diffOutput.replaceChildren();
      diffNote.hidden = true;
      try {{
        const response = await fileRequest(
          selectedFile.path,
          selectedFile.snapshot,
          true,
        );
        if (!response.ok) throw new Error(`Diff failed (${{response.status}})`);
        const details = await response.json();
        if (!details.sections.length) {{
          diffNote.textContent = "No textual diff is available for this file.";
          diffNote.hidden = false;
        }}
        for (const section of details.sections) {{
          const heading = document.createElement("h3");
          heading.textContent = section.label;
          const patch = renderDiffPatch(section.content);
          diffOutput.append(heading, patch);
        }}
        if (details.truncated) {{
          diffNote.textContent = "Diff truncated after 2,000 lines or 200 KB.";
          diffNote.hidden = false;
        }}
        showDiffButton.hidden = true;
      }} catch (error) {{
        diffNote.textContent = "Could not load this diff.";
        diffNote.hidden = false;
      }} finally {{
        showDiffButton.disabled = false;
        showDiffButton.textContent = "Show Diff";
      }}
    }}

    function renderDiffPatch(content) {{
      const patch = document.createElement("div");
      patch.className = "diff-patch";
      patch.setAttribute("role", "region");
      patch.setAttribute("aria-label", "Code changes");
      const metadataPrefixes = [
        "diff --git ", "index ", "--- ", "+++ ", "new file mode ",
        "deleted file mode ", "similarity index ", "rename from ",
        "rename to ", "Binary files ",
      ];
      for (const line of content.split("\\n")) {{
        const row = document.createElement("div");
        row.className = "diff-line";
        if (metadataPrefixes.some(prefix => line.startsWith(prefix))) {{
          row.classList.add("metadata");
        }} else if (line.startsWith("@@")) {{
          row.classList.add("hunk");
        }} else if (line.startsWith("+")) {{
          row.classList.add("added");
        }} else if (line.startsWith("-")) {{
          row.classList.add("deleted");
        }}
        row.textContent = line || " ";
        patch.append(row);
      }}
      return patch;
    }}

    workingButton.addEventListener("click", () => showSnapshot(0));
    branchPicker.addEventListener("change", () => {{
      historyRef = branchPicker.value;
      stateVersion = "";
      currentHistoryIndex = 0;
      refreshState(true);
    }});
    historyButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex));
    newerButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex - 1));
    olderButton.addEventListener("click", () => showSnapshot(historyStart + currentHistoryIndex + 1));
    showDiffButton.addEventListener("click", showSelectedDiff);
    fileInspectorBack.addEventListener("click", closeFilePanel);
    activityStatus.addEventListener("click", () => {{
      const path = activePaths[0];
      if (!path) return;
      const trace = graph.data[currentSnapshotIndex];
      const fileIndex = trace.ids?.indexOf(`file:${{path}}`) ?? -1;
      const status = fileIndex >= 0 ? trace.customdata?.[fileIndex]?.[1] : "changed";
      openFilePanel(path, status);
    }});
    graph.on("plotly_click", event => {{
      const point = event.points?.[0];
      if (point?.customdata?.[4] === "file") {{
        openFilePanel(point.customdata[0], point.customdata[1]);
      }} else {{
        closeFilePanel();
      }}
    }});
    window.addEventListener("resize", () => {{
      if (selectedFile && !positionFileInspector()) closeFilePanel();
      window.requestAnimationFrame(positionActivityRobots);
    }});
    graph.on("plotly_afterplot", () => window.requestAnimationFrame(positionActivityRobots));
    document.addEventListener("keydown", event => {{
      if (event.key === "Escape" && !fileInspector.hidden) closeFilePanel();
    }});
    window.addEventListener("popstate", () => {{
      if (!fileInspector.hidden) hideFilePanel();
    }});
    if (liveUpdates) {{
      refreshSessionStatus();
      window.setInterval(refreshState, 2500);
      window.setInterval(refreshSessionStatus, 2500);
    }}
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


def _branch_payload(branches: Iterable[BranchInfo]) -> list[dict[str, object]]:
    branch_list = list(branches)
    local_names = {branch.name for branch in branch_list if not branch.remote}
    remote_names: set[str] = set()
    payload = []

    for branch in branch_list:
        selectable = not branch.current
        if branch.remote:
            logical_name = branch.name.split("/", 1)[-1]
            selectable = (
                selectable
                and logical_name not in local_names
                and logical_name not in remote_names
            )
            remote_names.add(logical_name)
        payload.append({**branch.__dict__, "selectable": selectable})

    return payload


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
                    "revision": snapshot.commit.full_hash,
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
                "revision": snapshot.commit.full_hash,
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
