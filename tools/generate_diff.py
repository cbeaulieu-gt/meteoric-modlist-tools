"""
Side-by-side modlist diff generator.

Compares two JSON modlist files (exported via modlist_json_exporter MO2 plugin)
and generates a self-contained HTML file showing a visual side-by-side diff
with color-coded indicators for added, removed, moved, and updated mods.

Uses the same waterfall matching as generate_changelog.py (via modlist_utils),
plus section matching and positional alignment.

Usage:
    python generate_diff.py old_list.json new_list.json [-o output.html]
"""

import argparse
import difflib
import html
import sys
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import List, Optional, Tuple, Dict

from modlist_utils import (
    load_modlist,
    extract_mods,
    get_separator_order,
    get_version,
    match_mods,
    resolve_output_path,
    nexus_url,
    is_major_separator,
    major_display_name,
    name_key,
    same_name,
)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class ChangeType(Flag):
    UNCHANGED = 0
    ADDED = auto()
    REMOVED = auto()
    MOVED = auto()
    UPDATED = auto()


@dataclass
class SectionMatch:
    old_name: Optional[str]
    new_name: Optional[str]
    change: ChangeType  # UNCHANGED, ADDED, REMOVED, or MOVED (renamed)


@dataclass
class DiffRow:
    """A single row in the aligned diff output."""
    left_mod: Optional[dict] = None    # mod from old list (None if added)
    right_mod: Optional[dict] = None   # mod from new list (None if removed)
    change: ChangeType = ChangeType.UNCHANGED
    old_version: str = ""
    new_version: str = ""
    moved_from: str = ""    # section name the mod moved FROM (shown on right)
    moved_to: str = ""      # section name the mod moved TO (shown on left)
    is_section: bool = False  # True if this row is a section header
    section_match: Optional[SectionMatch] = None  # set when is_section=True


# ---------------------------------------------------------------------------
# Section Matching
# ---------------------------------------------------------------------------

def build_section_flow_matrix(matched_pairs):
    """
    Build a matrix counting how many matched mods flow from each old section
    to each new section.
    Returns {old_section: {new_section: count}}. Keys on both axes are
    case-insensitive section keys (see ``name_key``).
    """
    flow = {}
    for old_mod, new_mod in matched_pairs:
        old_sec = name_key(old_mod.get("separatorName", "Unsectioned"))
        new_sec = name_key(new_mod.get("separatorName", "Unsectioned"))
        if old_sec not in flow:
            flow[old_sec] = {}
        flow[old_sec][new_sec] = flow[old_sec].get(new_sec, 0) + 1
    return flow


def match_sections(old_sections, new_sections, matched_mod_pairs):
    """
    Match sections between old and new lists using a waterfall strategy:
    1. Exact name match
    2. Content-based match (mod flow matrix)
    3. Fuzzy name match

    Names are compared case-insensitively throughout (MO2 itself is), so a
    section merely recapitalized between exports matches in phase 1 rather than
    reading as one added plus one removed. The returned names keep each list's
    own spelling.

    Returns (matched_pairs, added_sections, removed_sections).
    matched_pairs is a list of (old_name, new_name).
    """
    matched = []
    matched_old = set()   # of name_key
    matched_new = set()   # of name_key

    # Phase 1: Exact name match (case-insensitive)
    new_by_key = {}
    for sec in new_sections:
        new_by_key.setdefault(name_key(sec), sec)
    for sec in old_sections:
        key = name_key(sec)
        if key in new_by_key and key not in matched_new:
            matched.append((sec, new_by_key[key]))
            matched_old.add(key)
            matched_new.add(key)

    # Phase 2: Content-based match using mod flow
    flow = build_section_flow_matrix(matched_mod_pairs)

    # Count mods per old section
    old_section_counts = {}
    for old_mod, _ in matched_mod_pairs:
        sec = name_key(old_mod.get("separatorName", "Unsectioned"))
        old_section_counts[sec] = old_section_counts.get(sec, 0) + 1

    unmatched_old = [s for s in old_sections if name_key(s) not in matched_old]
    unmatched_new = [s for s in new_sections if name_key(s) not in matched_new]

    for old_sec in list(unmatched_old):
        old_key = name_key(old_sec)
        if old_key not in flow:
            continue
        total = old_section_counts.get(old_key, 0)
        if total == 0:
            continue

        # Find the new section that received the most mods from this old section
        best_new = None
        best_count = 0
        unmatched_new_by_key = {name_key(s): s for s in unmatched_new}
        for new_key, count in flow[old_key].items():
            if new_key not in matched_new and new_key in unmatched_new_by_key:
                if count > best_count:
                    best_count = count
                    best_new = unmatched_new_by_key[new_key]

        if best_new and best_count / total >= 0.50:
            matched.append((old_sec, best_new))
            matched_old.add(old_key)
            matched_new.add(name_key(best_new))
            unmatched_old.remove(old_sec)
            unmatched_new.remove(best_new)

    # Phase 3: Fuzzy name match
    for old_sec in list(unmatched_old):
        best_new = None
        best_ratio = 0.0
        for new_sec in unmatched_new:
            ratio = difflib.SequenceMatcher(
                None, name_key(old_sec), name_key(new_sec)
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_new = new_sec
        if best_new and best_ratio >= 0.70:
            matched.append((old_sec, best_new))
            matched_old.add(name_key(old_sec))
            matched_new.add(name_key(best_new))
            unmatched_old.remove(old_sec)
            unmatched_new.remove(best_new)

    added = [s for s in new_sections if name_key(s) not in matched_new]
    removed = [s for s in old_sections if name_key(s) not in matched_old]

    return matched, added, removed


# ---------------------------------------------------------------------------
# Mod Classification
# ---------------------------------------------------------------------------

def classify_mod_changes(matched_pairs, section_match_map):
    """
    Classify each matched mod pair by what changed.

    section_match_map: {old_section_key: new_section_key} from section matching
    (case-insensitive keys — see ``name_key``).
    Returns list of (old_mod, new_mod, change_type, old_version, new_version).
    """
    results = []
    for old_mod, new_mod in matched_pairs:
        change = ChangeType.UNCHANGED
        old_ver = get_version(old_mod)
        new_ver = get_version(new_mod)

        # Check version change (only if both known)
        if old_ver != "Unknown" and new_ver != "Unknown" and old_ver != new_ver:
            change = change | ChangeType.UPDATED

        # Check section move
        old_sec = name_key(old_mod.get("separatorName", "Unsectioned"))
        new_sec = name_key(new_mod.get("separatorName", "Unsectioned"))
        resolved_new = section_match_map.get(old_sec)
        if resolved_new != new_sec:
            # Mod's new section is not the matched counterpart of its old section
            change = change | ChangeType.MOVED

        results.append((old_mod, new_mod, change, old_ver, new_ver))
    return results


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def get_mods_by_section(modlist_data):
    """
    Group mods by separatorName, preserving their original order within each section.
    Returns {section_key: [mod, ...]}, keyed case-insensitively (see ``name_key``)
    so a mod whose separatorName differs only in case from the separator item
    still lands in that section.
    """
    sections = {}
    for item in modlist_data:
        if item.get("type") != "mod":
            continue
        sec = name_key(item.get("separatorName", "Unsectioned"))
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(item)
    return sections


def align_sections(old_order, new_order, section_matches, added_sections, removed_sections):
    """
    Align sections following the NEW (right/target) list's order as primary.

    Removed old sections are inserted near their original context — just before
    the next old section that has a match in the new list.

    Returns list of SectionMatch objects.
    """
    # Keyed case-insensitively; values keep each list's own spelling.
    old_to_new = {name_key(old): new for old, new in section_matches}
    new_to_old = {name_key(new): old for old, new in section_matches}

    removed_set = {name_key(s) for s in removed_sections}

    # Build a map: for each matched old section, collect removed sections that
    # appeared just before it in the old list. These will be emitted before
    # that section's matched new counterpart.
    # removed_before[new_section_name] = [removed old sections to show before it]
    removed_before = {}
    pending_removed = []
    for old_sec in old_order:
        if name_key(old_sec) in removed_set:
            pending_removed.append(old_sec)
        elif name_key(old_sec) in old_to_new:
            new_name = name_key(old_to_new[name_key(old_sec)])
            if pending_removed:
                removed_before[new_name] = pending_removed
                pending_removed = []
    # Any remaining removed sections that came after all matched sections
    trailing_removed = pending_removed

    result = []
    for new_sec in new_order:
        # Emit any removed sections that belong before this one
        for rem in removed_before.get(name_key(new_sec), []):
            result.append(SectionMatch(rem, None, ChangeType.REMOVED))

        # Emit this new section
        if name_key(new_sec) in new_to_old:
            old_name = new_to_old[name_key(new_sec)]
            change = (ChangeType.UNCHANGED if same_name(old_name, new_sec)
                      else ChangeType.MOVED)
            result.append(SectionMatch(old_name, new_sec, change))
        else:
            result.append(SectionMatch(None, new_sec, ChangeType.ADDED))

    # Emit trailing removed sections at the end
    for rem in trailing_removed:
        result.append(SectionMatch(rem, None, ChangeType.REMOVED))

    return result


def align_mods_in_section(old_mods, new_mods, mod_match_lookup):
    """
    Align mods within a matched section pair, following the NEW list's mod order.

    Removed/moved-away old mods are inserted near their original context —
    just before the next old mod that has a match in this section.

    mod_match_lookup: {id(old_mod): (new_mod, change, old_ver, new_ver)}
                  and {("rev", id(new_mod)): (old_mod, change, old_ver, new_ver)}

    Returns list of DiffRow.
    """
    new_mod_set = {id(m) for m in new_mods}
    old_mod_set = {id(m) for m in old_mods}

    # Build reverse lookup: id(new_mod) -> old_mod in this section
    new_to_old_in_section = {}
    for old_mod in old_mods:
        info = mod_match_lookup.get(id(old_mod))
        if info and id(info[0]) in new_mod_set:
            new_to_old_in_section[id(info[0])] = old_mod

    # Build removed-before map: for each matched old mod, collect removed/moved-away
    # old mods that appeared just before it. These get emitted before that mod's
    # matched new counterpart.
    removed_before = {}  # id(new_mod) -> [DiffRow for removed old mods]
    pending_removed = []
    for old_mod in old_mods:
        info = mod_match_lookup.get(id(old_mod))
        if info and id(info[0]) in new_mod_set:
            # This old mod is matched to a new mod in this section
            new_mod_id = id(info[0])
            if pending_removed:
                removed_before[new_mod_id] = pending_removed
                pending_removed = []
        elif info and id(info[0]) not in new_mod_set:
            # Matched but moved to a different section
            new_mod, change, old_ver, new_ver = info
            pending_removed.append(DiffRow(
                left_mod=old_mod, right_mod=None,
                change=ChangeType.MOVED,
                old_version=old_ver, new_version=new_ver,
                moved_to=new_mod.get("separatorName", ""),
            ))
        else:
            # No match — removed
            pending_removed.append(DiffRow(
                left_mod=old_mod, right_mod=None,
                change=ChangeType.REMOVED,
            ))
    trailing_removed = pending_removed

    # Walk new mods in order, emitting contextual removed rows before each
    rows = []
    for new_mod in new_mods:
        # Emit any removed/moved-away old mods that belong before this one
        for rem_row in removed_before.get(id(new_mod), []):
            rows.append(rem_row)

        # Check if this new mod has a match
        rev_info = mod_match_lookup.get(("rev", id(new_mod)))
        if id(new_mod) in new_to_old_in_section:
            # Matched to an old mod in this section
            old_mod = new_to_old_in_section[id(new_mod)]
            info = mod_match_lookup[id(old_mod)]
            _, change, old_ver, new_ver = info
            rows.append(DiffRow(
                left_mod=old_mod, right_mod=new_mod,
                change=change,
                old_version=old_ver, new_version=new_ver,
            ))
        elif rev_info:
            old_mod_ref, change, old_ver, new_ver = rev_info
            if id(old_mod_ref) not in old_mod_set:
                # Moved in from another section
                rows.append(DiffRow(
                    left_mod=None, right_mod=new_mod,
                    change=ChangeType.MOVED | (ChangeType.UPDATED if ChangeType.UPDATED in change else ChangeType.UNCHANGED),
                    old_version=old_ver, new_version=new_ver,
                    moved_from=old_mod_ref.get("separatorName", ""),
                ))
            else:
                # Matched to an old mod in this section (shouldn't happen but safety)
                rows.append(DiffRow(
                    left_mod=old_mod_ref, right_mod=new_mod,
                    change=change,
                    old_version=old_ver, new_version=new_ver,
                ))
        else:
            # Truly added
            rows.append(DiffRow(
                left_mod=None, right_mod=new_mod,
                change=ChangeType.ADDED,
            ))

    # Emit trailing removed/moved-away old mods at the end of the section
    rows.extend(trailing_removed)

    return rows


def build_aligned_diff(old_data, new_data, matched_pairs, added_mods, removed_mods,
                        section_matches, added_sections, removed_sections,
                        section_match_map, mod_changes):
    """
    Build the full aligned diff as a list of DiffRow objects.
    """
    old_section_order = get_separator_order(old_data)
    new_section_order = get_separator_order(new_data)

    old_mods_by_section = get_mods_by_section(old_data)
    new_mods_by_section = get_mods_by_section(new_data)

    # Build mod match lookup for alignment
    # id(old_mod) -> (new_mod, change, old_ver, new_ver)
    # ("rev", id(new_mod)) -> (old_mod, change, old_ver, new_ver)
    mod_match_lookup = {}
    for old_mod, new_mod, change, old_ver, new_ver in mod_changes:
        mod_match_lookup[id(old_mod)] = (new_mod, change, old_ver, new_ver)
        mod_match_lookup[("rev", id(new_mod))] = (old_mod, change, old_ver, new_ver)

    # Also add removed mods (no match)
    # (They'll be handled by align_mods_in_section when not found in lookup)

    # Build section name mapping (case-insensitive keys)
    old_to_new = {name_key(old): new for old, new in section_matches}
    new_to_old = {name_key(new): old for old, new in section_matches}

    # Align sections
    aligned_sections = align_sections(
        old_section_order, new_section_order,
        section_matches, added_sections, removed_sections
    )

    rows = []
    for sec_match in aligned_sections:
        # Emit section header row
        rows.append(DiffRow(is_section=True, section_match=sec_match, change=sec_match.change))

        old_sec_mods = (old_mods_by_section.get(name_key(sec_match.old_name), [])
                        if sec_match.old_name else [])
        new_sec_mods = (new_mods_by_section.get(name_key(sec_match.new_name), [])
                        if sec_match.new_name else [])

        if sec_match.change == ChangeType.REMOVED:
            # All mods in this section are removed (unless they moved)
            for mod in old_sec_mods:
                info = mod_match_lookup.get(id(mod))
                if info:
                    new_mod, change, old_ver, new_ver = info
                    rows.append(DiffRow(
                        left_mod=mod, right_mod=None,
                        change=ChangeType.MOVED,
                        old_version=old_ver, new_version=new_ver,
                        moved_to=new_mod.get("separatorName", ""),
                    ))
                else:
                    rows.append(DiffRow(left_mod=mod, change=ChangeType.REMOVED))

        elif sec_match.change == ChangeType.ADDED:
            # All mods in this section are added (unless they moved in)
            for mod in new_sec_mods:
                rev_info = mod_match_lookup.get(("rev", id(mod)))
                if rev_info:
                    old_mod_ref, change, old_ver, new_ver = rev_info
                    rows.append(DiffRow(
                        left_mod=None, right_mod=mod,
                        change=ChangeType.MOVED | (ChangeType.UPDATED if ChangeType.UPDATED in change else ChangeType.UNCHANGED),
                        old_version=old_ver, new_version=new_ver,
                        moved_from=old_mod_ref.get("separatorName", ""),
                    ))
                else:
                    rows.append(DiffRow(right_mod=mod, change=ChangeType.ADDED))

        else:
            # Matched section pair — align mods within
            mod_rows = align_mods_in_section(old_sec_mods, new_sec_mods, mod_match_lookup)
            rows.extend(mod_rows)

    return rows


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def compute_summary(mod_changes, added_mods, removed_mods, section_matches,
                     added_sections, removed_sections):
    """Compute summary statistics for the diff."""
    moved = sum(1 for _, _, c, _, _ in mod_changes if ChangeType.MOVED in c)
    updated = sum(1 for _, _, c, _, _ in mod_changes if ChangeType.UPDATED in c)
    renamed_sections = sum(1 for old, new in section_matches if old != new)

    return {
        "added": len(added_mods),
        "removed": len(removed_mods),
        "moved": moved,
        "updated": updated,
        "sections_added": len(added_sections),
        "sections_removed": len(removed_sections),
        "sections_renamed": renamed_sections,
    }


# ---------------------------------------------------------------------------
# HTML Rendering
# ---------------------------------------------------------------------------

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
tr.filter-hidden { display: none; }
tr.section-header.filter-empty { display: none; }
.summary {
    display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px;
}
.summary .stat {
    padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600;
}
.stat-added { background: #1a3a2a; color: #4ade80; }
.stat-removed { background: #3a1a1a; color: #f87171; }
.stat-moved { background: #1a2a3a; color: #60a5fa; }
.stat-updated { background: #3a2a1a; color: #fb923c; }
.stat-sections { background: #2a1a3a; color: #c084fc; }

.legend {
    display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 24px;
    background: #1e1e36; border-bottom: 1px solid #333;
    font-size: 11px; color: #888;
}
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-color {
    width: 12px; height: 12px; border-radius: 2px; display: inline-block;
}

.diff-table {
    width: 100%; border-collapse: collapse;
}
.diff-table td {
    padding: 2px 12px; vertical-align: top; width: 50%;
    border-bottom: 1px solid #252540;
}
.diff-table td:first-child { border-right: 2px solid #0f3460; }

/* Section headers */
tr.section-header td {
    background: #1e2a4a; padding: 8px 12px; font-weight: 800;
    font-size: 14px; color: #cbd5e1; text-align: center;
    border-bottom: 2px solid #0f3460;
}
/* Major separators (dash-wrapped names) render as a divider band, matching the
   coverage report. Declared before the added/removed/renamed rules so those
   equal-specificity backgrounds still win on a changed major. */
tr.section-major td {
    background: #141d3a; color: #8aa0c8; text-align: center;
    font-weight: 800; letter-spacing: 2px; font-size: 11px; padding: 8px 12px;
    text-transform: uppercase;
    border-top: 1px solid #24345a; border-bottom: 1px solid #24345a;
}
/* An unchanged major spans both columns — no mid-table divider through it. */
tr.section-major td[colspan] { border-right: none; }
tr.section-added td { background: #0a2a1a; }
tr.section-removed td { background: #2a0a0a; }
tr.section-renamed td { background: #2a2a0a; }
tr.section-renamed .old-name { text-decoration: line-through; color: #888; }
tr.section-renamed .new-name { color: #fbbf24; }
tr.section-renamed .arrow { color: #666; margin: 0 6px; }

/* Mod rows */
tr.mod-unchanged td { color: #9ca3af; }
tr.mod-added td { background: #0a2a1a; }
tr.mod-added td:last-child { color: #4ade80; }
tr.mod-removed td { background: #2a0a0a; }
tr.mod-removed td:first-child { color: #f87171; }
tr.mod-moved td { background: #0a1a2e; }
tr.mod-moved .move-annotation {
    font-size: 11px; color: #60a5fa; font-style: italic; margin-left: 8px;
}
tr.mod-updated .version-change {
    font-size: 11px; color: #fb923c; margin-left: 8px;
}
tr.mod-moved-updated td { background: #1a1a2e; }
tr.mod-moved-updated .move-annotation { color: #60a5fa; }
tr.mod-moved-updated .version-change { color: #fb923c; }

td.empty { color: #444; }

/* Nexus links on changed mods — inherit the row's state color, reveal on hover
   so the added/removed/moved/updated color-coding stays intact. */
.diff-table a { color: inherit; text-decoration: none; }
.diff-table a:hover { text-decoration: underline; }

/* Striped for readability */
.diff-table tbody tr.mod-unchanged:nth-child(even) td {
    background: rgba(255,255,255,0.02);
}

/* Toggle control — pinned to the top-right of the centered 1024px column.
   On viewports wider than the column, (50% - 512px) is the gap to the right
   of the column; inset 16px inside it. Clamp to 16px on narrow viewports. */
.controls {
    position: fixed; top: 12px; z-index: 100;
    right: max(16px, calc(50% - 512px + 16px));
    display: flex; gap: 12px; align-items: center;
}
.toggle-btn {
    background: #0f3460; color: #e0e0e0; border: 1px solid #1a4a7a;
    border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 600;
    cursor: pointer; font-family: inherit;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.toggle-btn:hover { background: #16498a; }
.toggle-btn.active { background: #e94560; border-color: #e94560; color: #fff; }

/* When hiding unchanged mods, collapse those rows (section headers stay) */
body.hide-unchanged tr.mod-unchanged { display: none; }
"""


def _esc(text):
    """HTML-escape text."""
    return html.escape(str(text)) if text else ""


def _linked_name(name_html, mod, changed):
    """Wrap an (already-escaped) mod name in its Nexus link.

    Only changed mods link, and only when the mod carries a numeric Nexus page
    id; otherwise the name is returned as plain text. The link inherits the
    row's state color (see CSS), so the diff's color-coding is preserved.
    """
    url = nexus_url(mod) if changed else None
    if url:
        return f'<a href="{url}" target="_blank" rel="noopener">{name_html}</a>'
    return name_html


def render_html(rows, old_name, new_name, summary):
    """Render the aligned diff as a self-contained HTML file."""
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append(f"<title>Modlist Diff</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Controls — pinned top-right via fixed positioning
    parts.append('<div class="controls">')
    parts.append('<button id="toggle-unchanged" class="toggle-btn" onclick="toggleUnchanged()">Hide unchanged mods</button>')
    parts.append('</div>')

    # Header
    parts.append('<div class="header">')
    parts.append("<h1>Modlist Diff</h1>")
    parts.append(f'<div class="lists">Old: <span>{_esc(old_name)}</span> &nbsp;&mdash;&nbsp; New: <span>{_esc(new_name)}</span></div>')

    # Summary stats
    parts.append('<div class="summary">')
    parts.append(f'<span class="stat stat-added">+{summary["added"]} added</span>')
    parts.append(f'<span class="stat stat-removed">&minus;{summary["removed"]} removed</span>')
    parts.append(f'<span class="stat stat-moved">&harr; {summary["moved"]} moved</span>')
    parts.append(f'<span class="stat stat-updated">&uarr; {summary["updated"]} updated</span>')
    sec_changes = summary["sections_added"] + summary["sections_removed"] + summary["sections_renamed"]
    if sec_changes:
        parts.append(f'<span class="stat stat-sections">{sec_changes} section changes</span>')
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

    # Legend
    parts.append('<div class="legend">')
    for color, label in [("#4ade80", "Added"), ("#f87171", "Removed"),
                          ("#60a5fa", "Moved"), ("#fb923c", "Updated"),
                          ("#9ca3af", "Unchanged")]:
        parts.append(f'<span class="legend-item"><span class="legend-color" style="background:{color}"></span>{label}</span>')
    parts.append("</div>")

    # Diff table
    parts.append('<table class="diff-table"><tbody>')

    for row in rows:
        if row.is_section:
            _render_section_row(parts, row)
        else:
            _render_mod_row(parts, row)

    parts.append("</tbody></table>")

    # Toggle script
    parts.append("<script>")
    parts.append(
        "function toggleUnchanged() {"
        " var on = document.body.classList.toggle('hide-unchanged');"
        " var btn = document.getElementById('toggle-unchanged');"
        " btn.classList.toggle('active', on);"
        " btn.textContent = on ? 'Show unchanged mods' : 'Hide unchanged mods';"
        " refilter();"
        " }"
    )
    parts.append(
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
        "if(document.body.classList.contains('hide-unchanged')&&row.classList.contains('mod-unchanged'))return false;"
        "return true;}"
        "function applySectionVisibility(active){var hdr=null,any=false;"
        "function close(){if(hdr)hdr.classList.toggle('filter-empty',active&&!any);}"
        "var rows=document.querySelectorAll('.diff-table tr');"
        "rows.forEach(function(tr){"
        "if(tr.classList.contains('section-header')){close();any=false;"
        "hdr=tr.classList.contains('section-major')?null:tr;}"
        "else if(rowCounts(tr))any=true;});close();"
        # A major band survives while any section (or loose row) under it does.
        "rows.forEach(function(b){if(!b.classList.contains('section-major'))return;var vis=false;"
        "for(var el=b.nextElementSibling;el&&!el.classList.contains('section-major');el=el.nextElementSibling){"
        "if(el.classList.contains('section-header')){if(!el.classList.contains('filter-empty')){vis=true;break;}}"
        "else if(rowCounts(el)){vis=true;break;}}"
        "b.classList.toggle('filter-empty',active&&!vis);});}"
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

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_section_row(parts, row):
    """Render a section header row."""
    sm = row.section_match
    if not sm:
        return

    # A dash-wrapped "major" separator renders as a divider band: the decoration is
    # stripped and, when nothing about it changed, it spans both columns.
    major = is_major_separator(sm.old_name) or is_major_separator(sm.new_name)
    cls = "section-header section-major" if major else "section-header"

    def label(name):
        return _esc(major_display_name(name) if major else name)

    if sm.change == ChangeType.ADDED:
        parts.append(f'<tr class="{cls} section-added">')
        parts.append('<td class="empty"></td>')
        parts.append(f"<td>{label(sm.new_name)}</td>")
    elif sm.change == ChangeType.REMOVED:
        parts.append(f'<tr class="{cls} section-removed">')
        parts.append(f"<td>{label(sm.old_name)}</td>")
        parts.append('<td class="empty"></td>')
    elif not same_name(sm.old_name, sm.new_name):
        # Renamed
        parts.append(f'<tr class="{cls} section-renamed">')
        parts.append(f'<td><span class="old-name">{label(sm.old_name)}</span></td>')
        parts.append(f'<td><span class="new-name">{label(sm.new_name)}</span></td>')
    elif major:
        # Unchanged major: one full-width band.
        parts.append(f'<tr class="{cls}">')
        parts.append(f'<td colspan="2">{label(sm.new_name)}</td>')
    else:
        # Unchanged
        parts.append(f'<tr class="{cls}">')
        parts.append(f"<td>{label(sm.old_name)}</td>")
        parts.append(f"<td>{label(sm.new_name)}</td>")

    parts.append("</tr>")


def _render_mod_row(parts, row):
    """Render a mod diff row."""
    change = row.change

    # Determine row CSS class
    if ChangeType.MOVED in change and ChangeType.UPDATED in change:
        cls = "mod-moved-updated"
    elif ChangeType.MOVED in change:
        cls = "mod-moved"
    elif ChangeType.ADDED in change:
        cls = "mod-added"
    elif ChangeType.REMOVED in change:
        cls = "mod-removed"
    elif ChangeType.UPDATED in change:
        cls = "mod-updated"
    else:
        cls = "mod-unchanged"

    names = []
    for m in (row.left_mod, row.right_mod):
        if m:
            nl = (m.get("modName", "Unknown") or "Unknown").lower()
            if nl not in names:  # dedup: unchanged rows have the same name twice
                names.append(nl)
    data_names = _esc("\n".join(names))
    parts.append(f'<tr class="{cls}" data-names="{data_names}">')

    # Changed rows link the mod name to its Nexus page; unchanged rows stay plain.
    changed = change != ChangeType.UNCHANGED

    # Left cell (old mod)
    if row.left_mod:
        name = _linked_name(_esc(row.left_mod.get("modName", "Unknown")), row.left_mod, changed)
        annotations = []
        if row.moved_to:
            annotations.append(f'<span class="move-annotation">&rarr; {_esc(row.moved_to)}</span>')
        if ChangeType.UPDATED in change and row.left_mod and row.right_mod:
            annotations.append(f'<span class="version-change">{_esc(row.old_version)}</span>')
        parts.append(f"<td>{name}{''.join(annotations)}</td>")
    else:
        parts.append('<td class="empty"></td>')

    # Right cell (new mod)
    if row.right_mod:
        name = _linked_name(_esc(row.right_mod.get("modName", "Unknown")), row.right_mod, changed)
        annotations = []
        if row.moved_from:
            annotations.append(f'<span class="move-annotation">&larr; {_esc(row.moved_from)}</span>')
        if ChangeType.UPDATED in change:
            annotations.append(f'<span class="version-change">{_esc(row.old_version)} &rarr; {_esc(row.new_version)}</span>')
        parts.append(f"<td>{name}{''.join(annotations)}</td>")
    else:
        parts.append('<td class="empty"></td>')

    parts.append("</tr>")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a side-by-side HTML diff between two JSON modlist exports."
    )
    parser.add_argument("old_list", help="Path to old/base modlist JSON file")
    parser.add_argument("new_list", help="Path to new/updated modlist JSON file")
    parser.add_argument(
        "-o", "--output",
        help="Output HTML file, or a directory to auto-name the report inside it "
             "(<dir>/<new_list>/<old_list>.diff.html). Default: stdout.",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.80,
        help="Minimum confidence for fuzzy name matching (default: 0.80)",
    )
    args = parser.parse_args()

    # Load data
    old_data = load_modlist(args.old_list)
    new_data = load_modlist(args.new_list)

    old_mods = extract_mods(old_data)
    new_mods = extract_mods(new_data)

    # Match mods
    matched_pairs, added_mods, removed_mods = match_mods(old_mods, new_mods, args.min_confidence)

    # Match sections
    old_section_order = get_separator_order(old_data)
    new_section_order = get_separator_order(new_data)
    section_matches, added_sections, removed_sections = match_sections(
        old_section_order, new_section_order, matched_pairs
    )

    # Build section match map: old_key -> new_key (case-insensitive, see name_key)
    section_match_map = {name_key(old): name_key(new) for old, new in section_matches}

    # Classify mod changes
    mod_changes = classify_mod_changes(matched_pairs, section_match_map)

    # Build aligned diff
    rows = build_aligned_diff(
        old_data, new_data, matched_pairs, added_mods, removed_mods,
        section_matches, added_sections, removed_sections,
        section_match_map, mod_changes,
    )

    # Summary
    summary = compute_summary(
        mod_changes, added_mods, removed_mods,
        section_matches, added_sections, removed_sections,
    )

    # Derive list names from filenames
    import os
    old_name = os.path.splitext(os.path.basename(args.old_list))[0]
    new_name = os.path.splitext(os.path.basename(args.new_list))[0]

    # Render
    html_output = render_html(rows, old_name, new_name, summary)

    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "diff", "html")
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(html_output)
        print(f"Diff written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(html_output)


if __name__ == "__main__":
    main()
