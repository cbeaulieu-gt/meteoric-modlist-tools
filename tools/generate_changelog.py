"""
Standalone changelog generator for JSON modlist exports.

Compares two JSON modlist files (exported via modlist_json_exporter MO2 plugin)
and generates a markdown changelog showing added, removed, and updated mods.

Uses a multi-strategy waterfall matching approach:
  1. Nexus ID match
  2. Plugin-based match
  3. Strict normalized name match
  4. Fuzzy name match (difflib.SequenceMatcher)

Usage:
    python generate_changelog.py old_list.json new_list.json [-o output.md]
"""

import argparse
import sys

from modlist_utils import (
    load_modlist,
    extract_mods,
    get_separator_order,
    match_mods,
    classify_updates,
    resolve_output_path,
    name_key,
)


# ---------------------------------------------------------------------------
# Section Organization
# ---------------------------------------------------------------------------

def organize_by_section(mods, section_order):
    """
    Group mods by separatorName, preserving section order. Grouping is keyed
    case-insensitively (MO2 names are), with the first spelling seen used for
    display. Returns list of (section_name, sorted_mod_list).
    """
    section_mods = {}   # name_key -> [mod, ...]
    display = {}        # name_key -> display name
    for mod in mods:
        raw = mod.get("separatorName", "Unsectioned")
        key = name_key(raw)
        display.setdefault(key, raw)
        section_mods.setdefault(key, []).append(mod)

    # Sort mods within each section alphabetically
    for key in section_mods:
        section_mods[key].sort(key=lambda m: m.get("modName", "").lower())

    # Build ordered list following section_order
    ordered = []
    for section in section_order:
        key = name_key(section)
        if key in section_mods:
            ordered.append((section, section_mods.pop(key)))

    # Add any sections not in the known order
    for key, mods_list in sorted(section_mods.items()):
        ordered.append((display[key], mods_list))

    return ordered


# ---------------------------------------------------------------------------
# Markdown Generation
# ---------------------------------------------------------------------------

def generate_markdown(added_by_section, removed_by_section, updated, summary):
    """Generate the full markdown changelog string."""
    lines = []
    lines.append("# Modlist Changelog\n")
    lines.append("### Summary\n")
    lines.append(f"- **Added:** {summary['added']} mods")
    lines.append(f"- **Removed:** {summary['removed']} mods")
    lines.append(f"- **Updated:** {summary['updated']} mods")
    lines.append("")

    # Added Mods
    lines.append("## Added Mods\n")
    if added_by_section:
        for section, mods in added_by_section:
            lines.append(f"### {section}\n")
            for mod in mods:
                lines.append(f"- {mod.get('modName', 'Unknown')}")
            lines.append("")
    else:
        lines.append("No mods added.\n")

    # Removed Mods
    lines.append("## Removed Mods\n")
    if removed_by_section:
        for section, mods in removed_by_section:
            lines.append(f"### {section}\n")
            for mod in mods:
                lines.append(f"- {mod.get('modName', 'Unknown')}")
            lines.append("")
    else:
        lines.append("No mods removed.\n")

    # Updated Mods
    lines.append("## Updated Mods\n")
    if updated:
        for mod_name, old_ver, new_ver in updated:
            lines.append(f"- {mod_name}: {old_ver} \u2192 {new_ver}")
        lines.append("")
    else:
        lines.append("No mods updated.\n")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Library entry point
# ---------------------------------------------------------------------------

def generate(old_data, new_data, min_confidence=0.80):
    """Library entry point: render the markdown changelog for loaded modlist data.

    Pure data-in -> markdown-out; callers own all file IO and output naming.
    """
    old_mods = extract_mods(old_data)
    new_mods = extract_mods(new_data)
    old_section_order = get_separator_order(old_data)
    new_section_order = get_separator_order(new_data)
    matched, added, removed = match_mods(old_mods, new_mods, min_confidence)
    updated = classify_updates(matched)
    added_by_section = organize_by_section(added, new_section_order)
    removed_by_section = organize_by_section(removed, old_section_order)
    summary = {
        "added": len(added),
        "removed": len(removed),
        "updated": len(updated),
    }
    return generate_markdown(added_by_section, removed_by_section, updated, summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a changelog between two JSON modlist exports."
    )
    parser.add_argument("old_list", help="Path to old/base modlist JSON file")
    parser.add_argument("new_list", help="Path to new/updated modlist JSON file")
    parser.add_argument(
        "-o", "--output",
        help="Output markdown file, or a directory to auto-name the report inside it "
             "(<dir>/<new_list>/<old_list>.changelog.md). Default: stdout.",
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

    markdown = generate(old_data, new_data, min_confidence=args.min_confidence)

    out_path = resolve_output_path(args.output, args.old_list, args.new_list, "changelog", "md")
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(markdown)
        print(f"Changelog written to {out_path}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(markdown)


if __name__ == "__main__":
    main()
