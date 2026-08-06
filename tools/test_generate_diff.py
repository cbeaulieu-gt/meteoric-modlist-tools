"""Tests for generate_diff HTML rendering: sticky header, filter, data-names."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_diff
from generate_diff import (
    ChangeType,
    DiffRow,
    SectionMatch,
    align_sections,
    classify_mod_changes,
    get_mods_by_section,
    match_sections,
    render_html,
)
from modlist_utils import load_modlist


def _summary(**over):
    s = {
        "added": 0, "removed": 0, "moved": 0, "updated": 0,
        "sections_added": 0, "sections_removed": 0, "sections_renamed": 0,
    }
    s.update(over)
    return s


class RenderTest(unittest.TestCase):
    def setUp(self):
        # One unchanged mod, plus a "renamed" mod whose left/right names differ,
        # so we can assert both names land in a single data-names attribute.
        self.rows = [
            DiffRow(
                left_mod={"modName": "Skyland AIO"},
                right_mod={"modName": "Skyland AIO"},
                change=ChangeType.UNCHANGED,
            ),
            DiffRow(
                left_mod={"modName": "Old Faces 3D"},
                right_mod={"modName": "New Faces Thing"},
                change=ChangeType.UNCHANGED,
            ),
        ]
        self.html = render_html(self.rows, "Old List", "New List", _summary())

    def test_doctype(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))

    def test_header_is_sticky(self):
        match = re.search(r"\.header \{[^}]*\}", self.html)
        self.assertIsNotNone(match, "no .header CSS rule found")
        rule = match.group()
        self.assertIn("position: sticky", rule)
        self.assertIn("top: 0", rule)

    def test_filter_input_present(self):
        self.assertIn('id="filter-input"', self.html)
        self.assertIn('class="filter-input"', self.html)
        self.assertIn('type="search"', self.html)

    def test_filter_css_and_js(self):
        self.assertIn("tr.filter-hidden", self.html)
        self.assertIn("function filterMods", self.html)
        self.assertIn("'Escape'", self.html)

    def test_filter_clear_button(self):
        # The ✕ clear button sits inside the input's wrapper.
        self.assertIn('class="filter-wrap"', self.html)
        self.assertIn('id="filter-clear"', self.html)
        self.assertIn('aria-label="Clear filter"', self.html)
        # CSS: button styled + redundant native search clear suppressed.
        self.assertIn(".filter-clear", self.html)
        self.assertIn("-webkit-search-cancel-button", self.html)
        # JS: button is wired and the input is refocused after clearing.
        self.assertIn("filter-clear", self.html)
        self.assertIn("i.focus()", self.html)

    def test_rows_carry_data_names(self):
        self.assertIn('data-names="skyland aio"', self.html)

    def test_renamed_row_has_both_names_one_attr(self):
        # Either-name matching: both names in ONE attribute, newline-joined.
        self.assertIn('data-names="old faces 3d\nnew faces thing"', self.html)

    def test_section_filter_css_present(self):
        self.assertIn("tr.section-header.filter-empty", self.html)

    def test_section_visibility_js_present(self):
        self.assertIn("function applySectionVisibility", self.html)
        self.assertIn("function rowCounts", self.html)
        self.assertIn("function refilter", self.html)
        self.assertIn("applySectionVisibility(terms.length>0)", self.html)

    def test_rowcounts_accounts_for_hide_unchanged(self):
        # An unchanged row suppressed by Hide unchanged must not keep its section
        # header alive while a filter is active.
        self.assertIn("hide-unchanged", self.html)
        self.assertIn("mod-unchanged", self.html)

    def test_toggle_unchanged_refilters(self):
        self.assertIn("refilter();", self.html)


class NexusLinkTest(unittest.TestCase):
    """Changed mods link to their Nexus page; unchanged mods stay plain."""

    def _render(self, rows):
        return render_html(rows, "Old", "New", _summary())

    def test_added_mod_is_linked(self):
        html_out = self._render([
            DiffRow(right_mod={"modName": "New Mod", "id": 12345},
                    change=ChangeType.ADDED),
        ])
        self.assertIn(
            '<a href="https://www.nexusmods.com/skyrimspecialedition/mods/12345"'
            ' target="_blank" rel="noopener">New Mod</a>',
            html_out,
        )

    def test_removed_mod_is_linked(self):
        html_out = self._render([
            DiffRow(left_mod={"modName": "Gone Mod", "id": 777},
                    change=ChangeType.REMOVED),
        ])
        self.assertIn(
            'href="https://www.nexusmods.com/skyrimspecialedition/mods/777"',
            html_out,
        )

    def test_updated_mod_links_both_sides(self):
        html_out = self._render([
            DiffRow(left_mod={"modName": "SkyUI", "id": 12604},
                    right_mod={"modName": "SkyUI", "id": 12604},
                    change=ChangeType.UPDATED,
                    old_version="1.5", new_version="1.6"),
        ])
        # Both cells reference the same page id → the link appears twice.
        self.assertEqual(
            html_out.count(
                'href="https://www.nexusmods.com/skyrimspecialedition/mods/12604"'
            ),
            2,
        )

    def test_unchanged_mod_is_not_linked(self):
        html_out = self._render([
            DiffRow(left_mod={"modName": "Static Mod", "id": 55555},
                    right_mod={"modName": "Static Mod", "id": 55555},
                    change=ChangeType.UNCHANGED),
        ])
        self.assertNotIn("nexusmods.com", html_out)

    def test_changed_mod_without_id_is_not_linked(self):
        html_out = self._render([
            DiffRow(right_mod={"modName": "No Page Mod"},  # no numeric id
                    change=ChangeType.ADDED),
        ])
        self.assertNotIn("<a href", html_out)
        self.assertIn("No Page Mod", html_out)

    def test_link_css_present(self):
        html_out = self._render([])
        self.assertIn(".diff-table a", html_out)
        self.assertIn("color: inherit", html_out)


def _tbody(html_out):
    """Just the rendered rows — the CSS/JS boilerplate mentions every class name,
    so 'not in' assertions have to look at the table, not the whole document."""
    return html_out.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def _section_row(old_name, new_name, change=ChangeType.UNCHANGED):
    return DiffRow(
        is_section=True,
        section_match=SectionMatch(old_name, new_name, change),
        change=change,
    )


class MajorSeparatorRenderTest(unittest.TestCase):
    """Dash-wrapped separators render as a coverage-style divider band."""

    def _render(self, rows):
        return render_html(rows, "Old List", "New List", _summary())

    def test_unchanged_major_is_one_full_width_band(self):
        html_out = self._render([
            _section_row("---------- BASE ----------", "---------- BASE ----------"),
        ])
        self.assertIn('class="section-header section-major"', html_out)
        self.assertIn('<td colspan="2">BASE</td>', html_out)
        # Decoration is stripped, not escaped through.
        self.assertNotIn("---------- BASE ----------", _tbody(html_out))

    def test_changed_major_keeps_both_columns(self):
        html_out = self._render([
            _section_row(None, "--- NEW BAND ---", ChangeType.ADDED),
        ])
        self.assertIn("section-major section-added", html_out)
        self.assertIn("<td>NEW BAND</td>", html_out)
        self.assertNotIn('colspan="2"', _tbody(html_out))

    def test_ordinary_section_is_not_a_band(self):
        body = _tbody(self._render([_section_row("Core Fixes", "Core Fixes")]))
        self.assertNotIn("section-major", body)
        self.assertIn("<td>Core Fixes</td>", body)

    def test_recapitalized_section_is_not_reported_as_renamed(self):
        body = _tbody(self._render([_section_row("Core Fixes", "CORE FIXES")]))
        self.assertNotIn("section-renamed", body)
        # Each side keeps its own list's spelling.
        self.assertIn("<td>Core Fixes</td>", body)
        self.assertIn("<td>CORE FIXES</td>", body)

    def test_band_css_matches_coverage_style(self):
        html_out = self._render([])
        match = re.search(r"tr\.section-major td \{[^}]*\}", html_out)
        self.assertIsNotNone(match, "no tr.section-major CSS rule found")
        rule = match.group()
        self.assertIn("text-align: center", rule)
        self.assertIn("text-transform: uppercase", rule)
        self.assertIn("font-weight: 800", rule)
        self.assertIn("letter-spacing: 2px", rule)

    def test_section_headers_are_centered_and_bold(self):
        html_out = self._render([])
        match = re.search(r"tr\.section-header td \{[^}]*\}", html_out)
        self.assertIsNotNone(match, "no tr.section-header CSS rule found")
        rule = match.group()
        self.assertIn("text-align: center", rule)
        self.assertIn("font-weight: 800", rule)
        self.assertIn("color: #cbd5e1", rule)

    def test_band_visibility_js_scans_forward(self):
        # A band survives filtering while any section below it does.
        html_out = self._render([])
        self.assertIn("section-major", html_out)
        self.assertIn("nextElementSibling", html_out)


class CaseInsensitiveSectionTest(unittest.TestCase):
    """MO2 can't hold both 'Core' and 'CORE', so neither can our comparisons."""

    def test_recapitalized_section_matches_in_phase_one(self):
        matched, added, removed = match_sections(["Core"], ["CORE"], [])
        self.assertEqual(matched, [("Core", "CORE")])
        self.assertEqual(added, [])
        self.assertEqual(removed, [])

    def test_genuinely_new_section_still_reads_as_added(self):
        matched, added, removed = match_sections(["Core"], ["Core", "Extras"], [])
        self.assertEqual(added, ["Extras"])
        self.assertEqual(removed, [])

    def test_recapitalized_section_is_unchanged_not_moved(self):
        aligned = align_sections(["Core"], ["CORE"], [("Core", "CORE")], [], [])
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0].change, ChangeType.UNCHANGED)

    def test_mods_group_under_one_section_regardless_of_case(self):
        data = [
            {"type": "mod", "modName": "A", "separatorName": "Core"},
            {"type": "mod", "modName": "B", "separatorName": "CORE"},
        ]
        sections = get_mods_by_section(data)
        self.assertEqual(list(sections), ["core"])
        self.assertEqual(len(sections["core"]), 2)

    def test_recapitalized_section_is_not_a_move(self):
        old_mod = {"modName": "A", "separatorName": "Core", "version": "1.0"}
        new_mod = {"modName": "A", "separatorName": "CORE", "version": "1.0"}
        (_o, _n, change, _ov, _nv), = classify_mod_changes(
            [(old_mod, new_mod)], {"core": "core"})
        self.assertEqual(change, ChangeType.UNCHANGED)


EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    def test_generate_matches_committed_report(self):
        old = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        new = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        html = generate_diff.generate(old, new, "Example List 1.0", "Example List 1.1")
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.1", "Example List 1.0.diff.html"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(html, f.read())


if __name__ == "__main__":
    unittest.main()
