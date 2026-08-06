"""
Source-structured coverage view generator.

Renders one modlist (the SOURCE) organized by its own section structure,
highlighting which mods the TARGET list is missing or has at a different
version. Unlike generate_diff.py, load order is not considered — this compares
modlist *contents* through the lens of the source list's organization.

Reuses the pure-waterfall matching in modlist_utils (no ignore/alias/compendium
config files), consistent with generate_diff.py and generate_changelog.py.

Usage:
    python generate_coverage.py SOURCE.json TARGET.json [-o output.html]
"""

import argparse
import html
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from modlist_utils import (
    load_modlist,
    extract_mods,
    get_version,
    match_mods,
    compare_versions,
    plugin_set,
    resolve_output_path,
    is_major_separator,
    major_display_name,
    name_key,
    NEXUS_URL,
)
from coverage_ignore import is_ignored, resolve_ignore_path, load_ignore


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class CoverageState(Enum):
    ADD = "add"           # source mod not present in target (candidate to add)
    NEWER = "newer"       # source version > target version (actionable: pull in)
    DIFFERS = "differs"   # both known, differ, direction undeterminable (actionable)
    PLUGINS = "plugins"   # same/unknown version but plugin sets differ (actionable)
    REMOVED = "removed"   # (--base only) removed in the base update, still in target
    COMMON = "common"     # same version+plugins, source OLDER (target ahead), or unknown


# Synthetic section holding REMOVED rows, appended after all source sections.
REMOVED_SECTION = "Removed in base update"


@dataclass
class CoverageRow:
    mod: dict
    state: CoverageState
    source_version: str
    target_version: str          # "" when the mod is missing
    nexus_id: Optional[int]      # numeric Nexus id, or None
    target_name: str = ""        # matched target mod's modName; "" when unmatched
    ignored: bool = False
    plugins_added: tuple = ()    # sorted: in source, not target (you'd add these)
    plugins_removed: tuple = ()  # sorted: in target, not source (you'd remove these)
    base_note: str = ""          # --base mode: what changed in the base (tooltip)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def map_sections_to_majors(source_data):
    """Walk the source list in order, mapping each section (by case-insensitive
    ``name_key``) to the display name of the major separator in effect when it
    first appears (None before the first)."""
    section_majors = {}
    current_major = None
    for item in source_data:
        item_type = item.get("type")
        if item_type == "separator":
            name = item.get("separatorName") or ""
            if is_major_separator(name):
                current_major = major_display_name(name)
            section_majors.setdefault(name_key(name), current_major)
        elif item_type == "mod":
            name = item.get("separatorName") or "Unsectioned"
            section_majors.setdefault(name_key(name), current_major)
    return section_majors


def compute_base_changes(base_data, source_data, min_confidence=0.80):
    """Diff the old base list against the source (the new base).

    Returns (changed, removed_base_mods):

    - changed: dict keyed by id(source_mod), covering every source mod that is
      new or changed since the base — added mods, version changes (both versions
      known and compare_versions != 0; downgrades included), and plugin-set
      changes (which the version string can't see, and which work even when a
      version is Unknown). The value is a human-readable note about what changed
      ("New in base update", "Base: 1.2 → 1.5", "Base plugins: +a.esp"),
      rendered as a row tooltip. The id() keys are only valid for this same
      loaded source_data object — recompute after any reload.
    - removed_base_mods: base mods with no source match — candidates for the
      synthetic Removed section (the caller filters to target-present).
    """
    base_mods = extract_mods(base_data)
    source_mods = extract_mods(source_data)
    matched, added, removed = match_mods(base_mods, source_mods, min_confidence)

    changed = {}
    for src_mod in added:
        changed[id(src_mod)] = "New in base update"
    for base_mod, src_mod in matched:
        old_ver = get_version(base_mod)
        new_ver = get_version(src_mod)
        notes = []
        if (
            old_ver != "Unknown"
            and new_ver != "Unknown"
            and compare_versions(old_ver, new_ver) != 0
        ):
            notes.append(f"Base: {old_ver} → {new_ver}")
        old_plugins = plugin_set(base_mod)
        new_plugins = plugin_set(src_mod)
        if old_plugins != new_plugins:
            delta = [f"+{p}" for p in sorted(new_plugins - old_plugins)]
            delta += [f"−{p}" for p in sorted(old_plugins - new_plugins)]
            notes.append("Base plugins: " + " ".join(delta))
        if notes:
            changed[id(src_mod)] = "; ".join(notes)
    return changed, removed


def build_removed_rows(removed_base_mods, target_data, min_confidence=0.80,
                       ignore=None, exclude_target_ids=frozenset()):
    """Rows for mods removed in the base update that the target still carries.

    removed_base_mods are the base mods compute_base_changes found no source
    match for. Each is matched against the target; only target-present mods
    produce rows (a mod neither list has needs no action). The row keeps the
    base mod (name + Nexus link) and shows the target's version — that is
    what you'd be deleting.

    exclude_target_ids (id()s of target mods) suppresses rows for target mods
    already claimed by a still-present source mod — the source row's advice
    (update/common) wins over a contradictory "removed" row.
    """
    target_mods = extract_mods(target_data)
    matched, _added, _removed = match_mods(
        removed_base_mods, target_mods, min_confidence
    )
    rows = []
    for base_mod, target_mod in matched:
        if id(target_mod) in exclude_target_ids:
            continue  # a still-present source mod claims this target mod
        raw_id = base_mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None
        row = CoverageRow(
            base_mod,
            CoverageState.REMOVED,
            get_version(base_mod),
            get_version(target_mod),
            nexus_id,
            target_mod.get("modName", ""),
        )
        row.ignored = is_ignored(ignore, base_mod)
        rows.append(row)
    return rows


def build_report(source_data, target_data, min_confidence, ignore, base_data=None):
    """Assemble the full rows_by_section for a report.

    Without base_data this is exactly classify_source_mods. With it, the report
    is filtered to the base change set and a synthetic REMOVED_SECTION is
    appended for base-removed mods the target still carries (skipping target
    mods a still-present source mod already claims). Shared by the CLI and the
    serve-mode renderer so both build identical reports.
    """
    base_changes = None
    removed_rows = []
    matched = None
    if base_data is not None:
        base_changes, removed_base_mods = compute_base_changes(
            base_data, source_data, min_confidence
        )
        if removed_base_mods:
            # Target mods matched to any still-present source mod are not
            # "removed" — the source row's advice wins (see build_removed_rows).
            # The match is reused by classify_source_mods below (same loaded
            # dicts), so the expensive source-target matching runs once.
            matched, _added, _removed = match_mods(
                extract_mods(source_data), extract_mods(target_data), min_confidence
            )
            claimed = {id(t) for _s, t in matched}
            removed_rows = build_removed_rows(
                removed_base_mods, target_data, min_confidence, ignore,
                exclude_target_ids=claimed,
            )
    rows_by_section = classify_source_mods(
        source_data, target_data, min_confidence, ignore, base_changes,
        matched=matched,
    )
    if removed_rows:
        # REMOVED_SECTION is a synthetic key; a real source separator with the
        # same name would merge into it (accepted — vanishingly unlikely).
        # Placed at the top of the report: base removals are the most urgent
        # thing to act on in a rebase, so they lead rather than trail.
        rows_by_section[REMOVED_SECTION] = removed_rows
        rows_by_section.move_to_end(REMOVED_SECTION, last=False)
    return rows_by_section


def classify_source_mods(source_data, target_data, min_confidence=0.80, ignore=None,
                         base_changes=None, matched=None):
    """
    Classify every source mod against the target list.

    Returns an OrderedDict {section_name: [CoverageRow, ...]} keyed in the order
    sections first appear in the source list. Mods with no separator are grouped
    under "Unsectioned".

    base_changes (from compute_base_changes) restricts the report to mods that
    changed in the base update: source mods not in it are dropped entirely (their
    sections vanish when emptied), and kept rows carry the note in base_note.

    matched (precomputed match_mods(source_mods, target_mods) pairs) skips the
    internal matching run — pass it when the caller already computed the same
    match (the pairs must reference these same loaded mod dicts).
    """
    source_mods = extract_mods(source_data)
    target_mods = extract_mods(target_data)

    if matched is None:
        matched, _added, _removed = match_mods(source_mods, target_mods, min_confidence)
    match_lookup = {id(s): t for s, t in matched}

    rows_by_section = OrderedDict()
    # MO2 names are case-insensitive, so case variants of one separator collapse
    # onto the spelling seen first ({name_key: display name}).
    section_display = {}

    for mod in source_mods:
        if base_changes is not None and id(mod) not in base_changes:
            continue  # unchanged in the base update — not part of this report
        raw_section = mod.get("separatorName") or "Unsectioned"
        section = section_display.setdefault(name_key(raw_section), raw_section)
        if section not in rows_by_section:
            rows_by_section[section] = []

        # Cleaned versions (MO2 display format) for both display and comparison,
        # consistent with generate_diff.py / generate_changelog.py.
        source_version = get_version(mod)
        target_mod = match_lookup.get(id(mod))

        if target_mod is None:
            state = CoverageState.ADD
            target_version = ""
            src_plugins = tgt_plugins = frozenset()
        else:
            target_version = get_version(target_mod)
            src_plugins = plugin_set(mod)
            tgt_plugins = plugin_set(target_mod)
            plugins_differ = src_plugins != tgt_plugins

            if source_version == "Unknown" or target_version == "Unknown":
                # Versions can't speak; plugin drift is the only usable signal.
                state = (
                    CoverageState.PLUGINS if plugins_differ else CoverageState.COMMON
                )
            else:
                cmp = compare_versions(source_version, target_version)
                if cmp == 1:
                    # Source is newer — worth pulling into the target.
                    state = CoverageState.NEWER
                elif cmp is None:
                    # Direction undeterminable — keep actionable (might be newer).
                    state = CoverageState.DIFFERS
                elif cmp == 0 and plugins_differ:
                    # Right version, wrong plugin set — still work to do.
                    state = CoverageState.PLUGINS
                else:
                    # Equal with matching plugins, or source older (target ahead).
                    # Source-older stays Common even when plugins differ: the
                    # target is past the source, so matching an older source's
                    # plugin layout isn't a goal.
                    state = CoverageState.COMMON

        raw_id = mod.get("id")
        nexus_id = raw_id if isinstance(raw_id, int) else None

        target_name = target_mod.get("modName", "") if target_mod else ""
        row = CoverageRow(
            mod, state, source_version, target_version, nexus_id, target_name
        )
        row.ignored = is_ignored(ignore, mod)
        if state == CoverageState.PLUGINS:
            row.plugins_added = tuple(sorted(src_plugins - tgt_plugins))
            row.plugins_removed = tuple(sorted(tgt_plugins - src_plugins))
        if base_changes:
            row.base_note = base_changes.get(id(mod), "")
        rows_by_section[section].append(row)

    return rows_by_section


def compute_summary(rows_by_section):
    """Compute total, per-state, and ignored counts across all sections.

    Ignored rows are counted under "ignored" only — never under their underlying
    state — so the actionable stats reflect what still needs attention.
    """
    counts = {state: 0 for state in CoverageState}
    ignored = 0
    total = 0
    for rows in rows_by_section.values():
        for row in rows:
            total += 1
            if row.ignored:
                ignored += 1
            else:
                counts[row.state] += 1
    return {"total": total, "counts": counts, "ignored": ignored}


def coverage_percent(summary):
    """Floor percent of the source the target already 'handles'.

    Each mod is weighted by how done it is: common/ignored count full (1.0),
    newer/differs/plugins (present but at a different version or with a
    different plugin set) count half (0.5), and add/removed count zero.
    Returns None when there are no mods, so the header can render a dash
    instead of dividing by zero.
    """
    total = summary["total"]
    if not total:
        return None
    counts = summary["counts"]
    covered = (
        counts[CoverageState.COMMON]
        + summary["ignored"]
        + 0.5
        * (
            counts[CoverageState.NEWER]
            + counts[CoverageState.DIFFERS]
            + counts[CoverageState.PLUGINS]
        )
    )
    return int(100 * covered / total)  # int() floors for a non-negative ratio


# ---------------------------------------------------------------------------
# HTML Rendering
# ---------------------------------------------------------------------------

# Tooltip for the "% covered" badge — spells out the weighting so the number
# isn't a black box.
COVERED_TOOLTIP = (
    "Share of source mods the target already handles: "
    "have-it or ignored count full, different-version or different-plugins "
    "counts half, missing or base-removed count zero."
)

# Display order and labels for actionable states (used in badges/summary).
ACTIONABLE_STATES = [
    (CoverageState.ADD, "add"),
    (CoverageState.NEWER, "newer"),
    (CoverageState.DIFFERS, "differs"),
    (CoverageState.PLUGINS, "plugins"),
    (CoverageState.REMOVED, "removed"),
]

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #1a1a2e; color: #e0e0e0; font-size: 13px; line-height: 1.4;
    max-width: 1024px; margin: 0 auto 64px;
}
.header {
    position: sticky; top: 0; z-index: 50;
    background: #16213e; padding: 16px 24px; border-bottom: 2px solid #0f3460;
    box-shadow: 0 4px 12px rgba(0,0,0,0.45);
}
.header h1 { font-size: 20px; color: #e94560; margin-bottom: 8px; }
.header .lists { color: #a0a0b0; font-size: 13px; margin-bottom: 8px; }
.header .lists span { color: #e0e0e0; font-weight: 600; }
.filter-wrap { position: relative; margin-top: 10px; }
.filter-input {
    width: 100%; padding: 6px 10px; padding-right: 30px;
    background: #0f1830; color: #e0e0e0;
    border: 1px solid #1a4a7a; border-radius: 4px;
    font-family: inherit; font-size: 13px;
}
.filter-input::placeholder { color: #6b7a90; }
.filter-input::-webkit-search-cancel-button { display: none; }
.filter-clear {
    position: absolute; top: 50%; right: 6px; transform: translateY(-50%);
    background: none; border: none; padding: 2px 6px; cursor: pointer;
    color: #6b7a90; font-size: 16px; line-height: 1; font-family: inherit;
}
.filter-clear:hover { color: #e0e0e0; }
.mod-row.filter-hidden { display: none; }
.section.filter-empty, .section-body.bandless.filter-empty, .band.filter-empty { display: none; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; }
.summary .stat { padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.stat-covered { background: #1a4a7a; color: #e0e0e0; }
.stat-total { background: #2a2a3a; color: #cbd5e1; }
.stat-add { background: #0d2a16; color: #4ade80; }
.stat-newer { background: #3a2a1a; color: #fb923c; }
.stat-differs { background: #3a2f1a; color: #fbbf24; }
.stat-plugins { background: #241a3a; color: #a78bfa; }
.stat-removed { background: #2a0d12; color: #f87171; }
.stat-common { background: #232333; color: #9ca3af; }
.stat-ignored { background: #232333; color: #6b7280; }
/* Mirror the row icons on the summary badges. In CSS (not the text) so serve
   mode's setStat() textContent rewrites don't strip them. Each inherits its
   badge color; Total and Common stay text-only. */
.stat-add::before { content: "+ "; }
.stat-newer::before { content: "↑ "; }
.stat-differs::before { content: "≠ "; }
.stat-plugins::before { content: "± "; }
.stat-removed::before { content: "− "; }
.stat-ignored::before { content: "⊘ "; }

.controls {
    position: fixed; top: 12px; z-index: 100;
    right: max(16px, calc(50% - 512px + 16px));
    display: flex; gap: 8px; align-items: center;
}
.toggle-btn {
    background: #0f3460; color: #e0e0e0; border: 1px solid #1a4a7a;
    border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: 600;
    cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.toggle-btn:hover { background: #16498a; }
.toggle-btn.active { background: #e94560; border-color: #e94560; color: #fff; }

.section { border-bottom: 1px solid #252540; }
.section-header {
    position: sticky; top: var(--header-h, 0px); z-index: 40;
    background: #1e2a4a; padding: 8px 16px; font-weight: 700; font-size: 14px;
    color: #cbd5e1; cursor: pointer; user-select: none;
    display: flex; align-items: center; gap: 8px; border-bottom: 1px solid #0f3460;
}
.section-header:hover { background: #243456; }
.caret { color: #888; font-size: 11px; width: 12px; display: inline-block; transition: transform 0.1s; }
.section.collapsed .caret { transform: rotate(-90deg); }
.section.collapsed .section-body { display: none; }
.badge { font-size: 11px; font-weight: 600; color: #94a3b8; margin-left: auto; }
.band {
    background: #141d3a; color: #8aa0c8; text-align: center;
    font-weight: 800; letter-spacing: 2px; font-size: 11px; padding: 8px 12px;
    border-top: 1px solid #24345a; border-bottom: 1px solid #24345a;
}

.mod-row {
    padding: 3px 16px 3px 13px; display: flex; align-items: baseline; gap: 10px;
    border-left: 3px solid transparent;
}
/* Icon column: a fixed-width gutter aligning the per-row state glyph under the
   section-header caret (3px border + 13px padding = 16px = caret left edge;
   12px width matches .caret). Empty by default so Common rows reserve the
   column without a glyph and names stay aligned. */
.mod-row::before {
    content: ""; flex: none; width: 12px; text-align: center; font-weight: 700;
}
.mod-row a { color: inherit; text-decoration: none; }
.mod-row a:hover { text-decoration: underline; }
.mod-name { flex: 1; }
.src-alias { color: #8b94a8; font-size: 11px; font-style: italic; margin-left: 4px; }
.ver { font-size: 11px; white-space: nowrap; }

.mod-add { background: #0d2a16; border-left-color: #4ade80; color: #4ade80; }
.mod-newer  { background: #2a1c0a; border-left-color: #fb923c; }
.mod-newer .ver { color: #fb923c; }
.mod-differs { background: #2a240a; border-left-color: #fbbf24; }
.mod-differs .ver { color: #fbbf24; }
.mod-plugins { background: #221636; border-left-color: #a78bfa; }
.mod-plugins .ver { color: #a78bfa; }
.mod-removed { background: #2a0d12; border-left-color: #f87171; color: #f87171; }
.mod-common { color: #9ca3af; }
.mod-common .ver { color: #6b7280; }
.mod-ignored { color: #6b7280; }
.mod-ignored .ver { color: #5b6270; }

/* State glyphs in the icon column (Common shows none). Driven purely by the
   row's state class, so serve-mode's click-to-ignore class swap updates the
   icon with no JS change. */
.mod-add::before { content: "+"; color: #4ade80; }
.mod-newer::before { content: "↑"; color: #fb923c; }
.mod-differs::before { content: "≠"; color: #fbbf24; }
.mod-plugins::before { content: "±"; color: #a78bfa; }
.mod-removed::before { content: "−"; color: #f87171; }
.mod-ignored::before { content: "⊘"; color: #6b7280; }

body.hide-common .mod-common,
body.hide-common .mod-ignored { display: none; }

/* serve-mode only: these apply when render_html(serve=True) sets <body class="serve"> */
body.serve .mod-row { cursor: pointer; }
body.serve .mod-row:hover { background: #20203a; }
"""

_STATE_CSS = {
    CoverageState.ADD: "mod-add",
    CoverageState.NEWER: "mod-newer",
    CoverageState.DIFFERS: "mod-differs",
    CoverageState.PLUGINS: "mod-plugins",
    CoverageState.REMOVED: "mod-removed",
    CoverageState.COMMON: "mod-common",
}


def _esc(text):
    """HTML-escape text."""
    return html.escape(str(text)) if text else ""


def _section_state_counts(rows):
    counts = {state: 0 for state in CoverageState}
    ignored = 0
    for row in rows:
        if row.ignored:
            ignored += 1
        else:
            counts[row.state] += 1
    return counts, ignored


def _actionable_count(state_counts):
    return sum(state_counts[state] for state, _ in ACTIONABLE_STATES)


def _section_badge(state_counts):
    parts = [
        f"{state_counts[state]} {label}"
        for state, label in ACTIONABLE_STATES
        if state_counts[state]
    ]
    return " · ".join(parts) if parts else "all present"


def _name_html(row):
    source_name = row.mod.get("modName", "Unknown")
    target_name = row.target_name
    if target_name and target_name != source_name:
        # Target name (what the reader knows it as) is primary; the source's
        # label follows in a muted alias span. Both sit inside the one link.
        inner = (
            f'{_esc(target_name)}'
            f'<span class="src-alias">({_esc(source_name)})</span>'
        )
    else:
        inner = _esc(source_name)
    if row.nexus_id is not None:
        url = NEXUS_URL.format(id=row.nexus_id)
        return f'<a href="{url}" target="_blank" rel="noopener">{inner}</a>'
    return inner


def _version_html(row):
    state = row.state
    src = _esc(row.source_version) if row.source_version != "Unknown" else ""
    tgt = _esc(row.target_version) if row.target_version != "Unknown" else ""
    if state == CoverageState.NEWER:
        # Read as the upgrade you'd make: your (target) version -> candidate (source).
        return f"{tgt} → {src}"
    if state == CoverageState.DIFFERS:
        # Source-driven report: lead with the candidate (source) version.
        return f"{src} ≠ {tgt}"
    if state == CoverageState.REMOVED:
        # The target still carries it; show the version you'd be deleting.
        return tgt
    if state == CoverageState.PLUGINS:
        # Version is right (or unknowable); the actionable bit is the delta.
        delta = _esc(_plugin_delta_text(row))
        return f"{src} {delta}".strip() if src else delta
    # ADD and COMMON (incl. source-older / target-ahead): show the source version.
    return src


# Inline plugin-delta cap: up to this many names render in the row; larger
# deltas collapse to counts, with the full list always in the tooltip.
_DELTA_INLINE_LIMIT = 3


def _plugin_delta_parts(row):
    """['+x.esp', ...] + ['−y.esp', ...] — the change the target would make
    to match the source (add what it lacks, remove what the source dropped)."""
    return [f"+{p}" for p in row.plugins_added] + [
        f"−{p}" for p in row.plugins_removed
    ]


def _plugin_delta_text(row):
    """Compact inline delta: names up to the cap, then counts ('+4 −2 plugins')."""
    parts = _plugin_delta_parts(row)
    if len(parts) <= _DELTA_INLINE_LIMIT:
        return " ".join(parts)
    counts = []
    if row.plugins_added:
        counts.append(f"+{len(row.plugins_added)}")
    if row.plugins_removed:
        counts.append(f"−{len(row.plugins_removed)}")
    return " ".join(counts) + " plugins"


def _render_mod_row(parts, row, serve=False):
    cls = "mod-ignored" if row.ignored else _STATE_CSS[row.state]
    ver = _version_html(row)
    tips = []
    if row.state == CoverageState.PLUGINS:
        tips.append(" ".join(_plugin_delta_parts(row)))
    if row.base_note:
        tips.append(row.base_note)
    tip_attr = f' title="{_esc(" | ".join(tips))}"' if tips else ""
    ver_html = f'<span class="ver"{tip_attr}>{ver}</span>' if ver else ""
    names = [(row.mod.get("modName", "") or "").lower()]
    target_lower = (row.target_name or "").lower()
    if target_lower and target_lower != names[0]:
        names.append(target_lower)
    data_names = _esc("\n".join(names))
    attrs = f' data-names="{data_names}"'
    if serve:
        name = _esc(row.mod.get("modName", ""))
        state_cls = _STATE_CSS[row.state]
        flag = "1" if row.ignored else "0"
        action = "un-ignore" if row.ignored else "ignore"
        attrs += (
            f' data-mod="{name}" data-state="{state_cls}" data-ignored="{flag}"'
            f' title="Click to {action}"'
        )
    parts.append(f'<div class="mod-row {cls}"{attrs}>')
    parts.append(f'<span class="mod-name">{_name_html(row)}</span>')
    parts.append(ver_html)
    parts.append("</div>")


def _render_band(parts, display_name):
    parts.append(f'<div class="band">{_esc(display_name)}</div>')


def _render_bandless_rows(parts, rows, serve=False):
    # Mods sitting directly under a major separator: rows render beneath the band
    # with no sub-header (the band is their header).
    parts.append('<div class="section-body bandless">')
    for row in rows:
        _render_mod_row(parts, row, serve)
    parts.append("</div>")


def _render_section(parts, section_name, rows, serve=False):
    state_counts, _ignored = _section_state_counts(rows)
    collapsed = "" if _actionable_count(state_counts) else " collapsed"
    badge = _esc(_section_badge(state_counts))
    parts.append(f'<div class="section{collapsed}">')
    parts.append('<div class="section-header" onclick="toggleSection(this)">')
    parts.append('<span class="caret">▾</span>')
    parts.append(f"<span>{_esc(section_name)}</span>")
    parts.append(f'<span class="badge">{badge}</span>')
    parts.append("</div>")
    parts.append('<div class="section-body">')
    for row in rows:
        _render_mod_row(parts, row, serve)
    parts.append("</div>")
    parts.append("</div>")


def render_html(rows_by_section, summary, source_name, target_name,
                section_majors=None, serve=False, base_name=None):
    """Render the coverage view as a self-contained HTML document."""
    section_majors = section_majors or {}
    counts = summary["counts"]
    title = "Base Update Coverage" if base_name else "Modlist Coverage"
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append(f"<title>{title}</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("</head>")
    parts.append('<body class="serve">' if serve else "<body>")

    # Controls
    parts.append('<div class="controls">')
    parts.append('<button class="toggle-btn" onclick="expandAll()">Expand all</button>')
    parts.append('<button class="toggle-btn" onclick="collapseAll()">Collapse all</button>')
    parts.append('<button id="toggle-common" class="toggle-btn" onclick="toggleCommon()">Hide common mods</button>')
    parts.append("</div>")

    # Header + summary
    parts.append('<div class="header">')
    parts.append(f"<h1>{title}</h1>")
    if base_name:
        parts.append(
            f'<div class="lists">Base update: <span>{_esc(base_name)}</span>'
            f' → <span>{_esc(source_name)}</span>'
            f' &nbsp;·&nbsp; applied to: <span>{_esc(target_name)}</span></div>'
        )
    else:
        parts.append(
            f'<div class="lists">Source: <span>{_esc(source_name)}</span>'
            f' &nbsp;vs&nbsp; Target: <span>{_esc(target_name)}</span></div>'
        )
    parts.append('<div class="summary">')
    pct = coverage_percent(summary)
    pct_text = f"{pct}% covered" if pct is not None else "— covered"
    parts.append(
        f'<span id="stat-covered" class="stat stat-covered" '
        f'title="{_esc(COVERED_TOOLTIP)}">{pct_text}</span>'
    )
    parts.append(f'<span class="stat stat-total">{summary["total"]} mods</span>')
    parts.append(f'<span id="stat-add" class="stat stat-add">{counts[CoverageState.ADD]} to add</span>')
    parts.append(f'<span id="stat-newer" class="stat stat-newer">{counts[CoverageState.NEWER]} newer</span>')
    parts.append(f'<span id="stat-differs" class="stat stat-differs">{counts[CoverageState.DIFFERS]} differs</span>')
    parts.append(f'<span id="stat-plugins" class="stat stat-plugins">{counts[CoverageState.PLUGINS]} plugins</span>')
    if base_name:
        parts.append(f'<span id="stat-removed" class="stat stat-removed">{counts[CoverageState.REMOVED]} removed</span>')
    parts.append(f'<span id="stat-ignored" class="stat stat-ignored">{summary.get("ignored", 0)} ignored</span>')
    parts.append(f'<span id="stat-common" class="stat stat-common">{counts[CoverageState.COMMON]} common</span>')
    parts.append("</div>")
    parts.append(
        '<div class="filter-wrap">'
        '<input type="search" id="filter-input" class="filter-input" '
        'placeholder="Filter mods… (space = AND)" autocomplete="off">'
        '<button type="button" id="filter-clear" class="filter-clear" '
        'aria-label="Clear filter" hidden>&times;</button>'
        '</div>'
    )
    parts.append("</div>")

    # Sections, with a divider band emitted whenever the major section changes.
    prev_major = object()  # sentinel: distinct from any real value, including None
    for section_name, rows in rows_by_section.items():
        major = section_majors.get(name_key(section_name))
        if major != prev_major:
            if major:
                _render_band(parts, major)
            prev_major = major
        if is_major_separator(section_name):
            _render_bandless_rows(parts, rows, serve)
        else:
            _render_section(parts, section_name, rows, serve)

    # Scripts
    parts.append("<script>")
    parts.append(
        "function toggleSection(h){h.parentElement.classList.toggle('collapsed');}"
        "function expandAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.remove('collapsed');});}"
        "function collapseAll(){document.querySelectorAll('.section').forEach(function(s){s.classList.add('collapsed');});}"
        "function toggleCommon(){var on=document.body.classList.toggle('hide-common');"
        "var b=document.getElementById('toggle-common');b.classList.toggle('active',on);"
        "b.textContent=on?'Show common mods':'Hide common mods';refilter();}"
        "function setHeaderH(){var h=document.querySelector('.header');"
        "if(h)document.documentElement.style.setProperty('--header-h',h.offsetHeight+'px');}"
        "window.addEventListener('resize',setHeaderH);setHeaderH();"
        "function filterMods(q){"
        "var terms=(q||'').trim().toLowerCase().split(/\\s+/).filter(Boolean);"
        "document.querySelectorAll('[data-names]').forEach(function(row){"
        "var hide=false;"
        "if(terms.length){var names=row.getAttribute('data-names').split('\\n');"
        "hide=!names.some(function(n){return terms.every(function(t){return n.indexOf(t)!==-1;});});}"
        "row.classList.toggle('filter-hidden',hide);});"
        "applySectionVisibility(terms.length>0);}"
        "function rowCounts(row){"
        "if(row.classList.contains('filter-hidden'))return false;"
        "if(document.body.classList.contains('hide-common')&&(row.classList.contains('mod-common')||row.classList.contains('mod-ignored')))return false;"
        "return true;}"
        "function unitHasMatch(u){var rows=u.querySelectorAll('.mod-row');"
        "for(var i=0;i<rows.length;i++)if(rowCounts(rows[i]))return true;return false;}"
        "function applySectionVisibility(active){"
        "document.querySelectorAll('.section, .section-body.bandless').forEach(function(u){"
        "u.classList.toggle('filter-empty',active&&!unitHasMatch(u));});"
        "document.querySelectorAll('.band').forEach(function(b){var any=false;"
        "for(var el=b.nextElementSibling;el&&!el.classList.contains('band');el=el.nextElementSibling){"
        "if((el.classList.contains('section')||el.classList.contains('bandless'))&&!el.classList.contains('filter-empty')){any=true;break;}}"
        "b.classList.toggle('filter-empty',active&&!any);});}"
        "function refilter(){var i=document.getElementById('filter-input');filterMods(i?i.value:'');}"
        "(function(){var i=document.getElementById('filter-input');if(!i)return;"
        "var c=document.getElementById('filter-clear');"
        "function sync(){if(c)c.hidden=!i.value;}"
        "i.addEventListener('input',function(){filterMods(this.value);sync();});"
        "i.addEventListener('keydown',function(e){if(e.key==='Escape'){this.value='';filterMods('');sync();}});"
        "if(c)c.addEventListener('click',function(){i.value='';filterMods('');sync();i.focus();});"
        "sync();})();"
    )
    parts.append("</script>")

    if serve:
        parts.append("<script>")
        parts.append(
            "(function(){"
            "function setStat(id,t){var e=document.getElementById(id);if(e)e.textContent=t;}"
            "function recount(){"
            "var c={add:0,newer:0,differs:0,plugins:0,removed:0,common:0,ignored:0};"
            "document.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-ignored'))c.ignored++;"
            "else if(r.classList.contains('mod-add'))c.add++;"
            "else if(r.classList.contains('mod-newer'))c.newer++;"
            "else if(r.classList.contains('mod-differs'))c.differs++;"
            "else if(r.classList.contains('mod-plugins'))c.plugins++;"
            "else if(r.classList.contains('mod-removed'))c.removed++;"
            "else if(r.classList.contains('mod-common'))c.common++;});"
            "setStat('stat-add',c.add+' to add');setStat('stat-newer',c.newer+' newer');"
            "setStat('stat-differs',c.differs+' differs');"
            "setStat('stat-plugins',c.plugins+' plugins');"
            "setStat('stat-removed',c.removed+' removed');"
            "setStat('stat-ignored',c.ignored+' ignored');"
            "setStat('stat-common',c.common+' common');"
            "var tot=c.add+c.newer+c.differs+c.plugins+c.removed+c.common+c.ignored;"
            "var pct=tot?Math.floor(100*(c.common+c.ignored+0.5*(c.newer+c.differs+c.plugins))/tot):null;"
            "setStat('stat-covered',pct===null?'\\u2014 covered':pct+'% covered');"
            "document.querySelectorAll('.section').forEach(function(s){"
            "var a=0,n=0,d=0,p=0,rm=0;"
            "s.querySelectorAll('.mod-row').forEach(function(r){"
            "if(r.classList.contains('mod-add'))a++;"
            "else if(r.classList.contains('mod-newer'))n++;"
            "else if(r.classList.contains('mod-differs'))d++;"
            "else if(r.classList.contains('mod-plugins'))p++;"
            "else if(r.classList.contains('mod-removed'))rm++;});"
            "var act=a+n+d+p+rm;s.classList.toggle('collapsed',act===0);"
            "var b=s.querySelector('.badge');if(b)"
            "b.textContent=(a?[a+' add']:[]).concat(n?[n+' newer']:[],d?[d+' differs']:[],p?[p+' plugins']:[],rm?[rm+' removed']:[]).join(' \\u00b7 ')||'all present';});}"
            "function setIgnored(row,on){var sc=row.getAttribute('data-state');"
            "row.classList.remove('mod-add','mod-newer','mod-differs','mod-plugins','mod-removed','mod-common','mod-ignored');"
            "row.classList.add(on?'mod-ignored':sc);"
            "row.setAttribute('data-ignored',on?'1':'0');"
            "row.setAttribute('title','Click to '+(on?'un-ignore':'ignore'));}"
            "document.body.addEventListener('click',function(e){"
            "if(e.target.closest('a'))return;"
            "var row=e.target.closest('.mod-row');if(!row)return;"
            "var name=row.getAttribute('data-mod');if(name===null)return;"
            "var on=row.getAttribute('data-ignored')==='1';"
            "fetch('/api/ignore',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({name:name,ignored:!on})})"
            ".then(function(r){return r.json();}).then(function(d){"
            "if(!d.ok)return;setIgnored(row,!on);recount();refilter();}).catch(function(){});});"
            "})();"
        )
        parts.append("</script>")
    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate a source-structured HTML coverage view: shows the SOURCE "
            "list's mods (grouped by its sections) and highlights what the TARGET "
            "list is missing or has at a different version."
        )
    )
    parser.add_argument("source", help="Path to the source modlist JSON (the list being inspected)")
    parser.add_argument("target", help="Path to the target modlist JSON (your list)")
    parser.add_argument(
        "-o", "--output",
        help="Output HTML file, or a directory to auto-name the report inside it "
             "(<dir>/<target>/<source>.coverage.html). Default: stdout.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.80,
        help="Minimum confidence for fuzzy name matching (default: 0.80)",
    )
    parser.add_argument(
        "--base",
        help="Path to the OLD base modlist JSON. Filters the report to mods "
             "that changed between it and SOURCE (the new base), adds a "
             "'Removed in base update' section, and switches output naming to "
             "<source> (from <base>).rebase.html.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start a local click-to-ignore server instead of writing a static report.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for --serve (default: 8000; auto-increments if busy). Ignored without --serve.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open the browser in --serve mode.",
    )
    parser.add_argument(
        "--ignore-file",
        help="Path to the per-target ignore file (default: <output-dir>/<target>/.coverage-ignore.txt; none when writing to stdout).",
    )
    args = parser.parse_args()

    ignore_path = args.ignore_file or resolve_ignore_path(args.output, args.target)

    if args.serve:
        from coverage_server import serve

        serve(
            source_path=args.source,
            target_path=args.target,
            min_confidence=args.min_confidence,
            ignore_path=ignore_path,
            port=args.port,
            open_browser=not args.no_browser,
            base_path=args.base,
        )
        return

    source_data = load_modlist(args.source)
    target_data = load_modlist(args.target)
    ignore = load_ignore(ignore_path)

    base_data = None
    base_name = None
    if args.base:
        base_data = load_modlist(args.base)
        base_name = os.path.splitext(os.path.basename(args.base))[0]

    rows_by_section = build_report(
        source_data, target_data, args.min_confidence, ignore, base_data
    )
    summary = compute_summary(rows_by_section)
    section_majors = map_sections_to_majors(source_data)

    source_name = os.path.splitext(os.path.basename(args.source))[0]
    target_name = os.path.splitext(os.path.basename(args.target))[0]

    html_output = render_html(
        rows_by_section, summary, source_name, target_name, section_majors,
        base_name=base_name,
    )

    if args.base:
        out_path = resolve_output_path(
            args.output, args.source, args.target, "rebase", "html",
            first_name=f"{source_name} (from {base_name})",
        )
    else:
        out_path = resolve_output_path(
            args.output, args.source, args.target, "coverage", "html"
        )
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(html_output)
        print(f"Coverage view written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)


if __name__ == "__main__":
    main()
