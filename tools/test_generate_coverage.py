"""Tests for generate_coverage classification and summary."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_coverage
from generate_coverage import (
    CoverageState,
    classify_source_mods,
    compute_summary,
    coverage_percent,
    render_html,
)
from modlist_utils import load_modlist
from coverage_ignore import load_ignore


def make_summary(total, add=0, newer=0, differs=0, plugins=0, removed=0, common=0,
                 ignored=0):
    """Build a summary dict shaped like compute_summary's output."""
    return {
        "total": total,
        "ignored": ignored,
        "counts": {
            CoverageState.ADD: add,
            CoverageState.NEWER: newer,
            CoverageState.DIFFERS: differs,
            CoverageState.PLUGINS: plugins,
            CoverageState.REMOVED: removed,
            CoverageState.COMMON: common,
        },
    }


def sep(name, order):
    return {"type": "separator", "separatorName": name, "order": order}


def mod(name, order, separator, version=None, nexus_id=None, plugins=None):
    item = {
        "type": "mod",
        "modName": name,
        "order": order,
        "separatorName": separator,
    }
    if version is not None:
        item["general"] = {"version": version}
    if nexus_id is not None:
        item["id"] = nexus_id
    if plugins is not None:
        item["plugins"] = plugins
    return item


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        # Source list: 2 sections, 4 mods covering each state.
        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5.0", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0.0", nexus_id=99999),
            sep("Visuals", 3),
            mod("ENB Helper", 4, "Visuals", version="1.5.0", nexus_id=23174),
            mod("SameMod", 5, "Visuals", version="3.0.0", nexus_id=11111),
        ]
        # Target: has Valhalla (older), ENB Helper (newer), SameMod (equal).
        self.target = [
            sep("Gameplay", 0),
            mod("Valhalla Combat", 1, "Gameplay", version="1.4.0", nexus_id=64741),
            mod("ENB Helper SE", 2, "Gameplay", version="1.6.0", nexus_id=23174),
            mod("SameMod", 3, "Gameplay", version="3.0.0", nexus_id=11111),
        ]

    def _state_of(self, rows_by_section, mod_name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == mod_name:
                    return row
        raise AssertionError(f"{mod_name} not found")

    def test_newer(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "Valhalla Combat")
        self.assertEqual(row.state, CoverageState.NEWER)
        # Versions are stored cleaned (MO2 display format): "1.5.0" -> "1.5".
        self.assertEqual(row.source_version, "1.5")
        self.assertEqual(row.target_version, "1.4")

    def test_source_older_is_common(self):
        # Source older than target (target already ahead) is not actionable,
        # so it is treated as Common.
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "ENB Helper")
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_common(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "SameMod")
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_add(self):
        result = classify_source_mods(self.source, self.target)
        row = self._state_of(result, "MissingMod")
        self.assertEqual(row.state, CoverageState.ADD)
        self.assertEqual(row.target_version, "")
        self.assertEqual(row.nexus_id, 99999)

    def test_section_order_and_keys(self):
        result = classify_source_mods(self.source, self.target)
        self.assertEqual(list(result.keys()), ["Combat", "Visuals"])

    def test_unsectioned(self):
        source = [mod("Orphan", 0, "")]  # no separator
        result = classify_source_mods(source, [])
        self.assertIn("Unsectioned", result)

    def test_unknown_version_is_common(self):
        source = [sep("S", 0), mod("X", 1, "S", nexus_id=42)]  # no version
        target = [sep("T", 0), mod("X", 1, "T", version="2.0", nexus_id=42)]
        result = classify_source_mods(source, target)
        row = self._state_of(result, "X")
        self.assertEqual(row.state, CoverageState.COMMON)


class TargetNameTest(unittest.TestCase):
    def setUp(self):
        # ENB Helper (source) is named "ENB Helper SE" in the target -> renamed match.
        self.source = [
            sep("Visuals", 0),
            mod("ENB Helper", 1, "Visuals", version="1.5.0", nexus_id=23174),
            mod("SameMod", 2, "Visuals", version="3.0.0", nexus_id=11111),
            mod("MissingMod", 3, "Visuals", version="2.0.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("ENB Helper SE", 1, "T", version="1.6.0", nexus_id=23174),
            mod("SameMod", 2, "T", version="3.0.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)

    def _row(self, name):
        for rows in self.rows.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def test_matched_renamed_carries_target_name(self):
        self.assertEqual(self._row("ENB Helper").target_name, "ENB Helper SE")

    def test_matched_same_name_carries_target_name(self):
        # Even when identical, the field is populated (render decides whether to show it).
        self.assertEqual(self._row("SameMod").target_name, "SameMod")

    def test_unmatched_has_empty_target_name(self):
        self.assertEqual(self._row("MissingMod").target_name, "")


class RenderTargetNameTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("Visuals", 0),
            # Renamed match: source "ENB Helper" vs target "ENB Helper SE".
            mod("ENB Helper", 1, "Visuals", version="1.5", nexus_id=23174),
            # Same-name match.
            mod("SameMod", 2, "Visuals", version="3.0", nexus_id=11111),
            # Unmatched -> Add.
            mod("MissingMod", 3, "Visuals", version="2.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("ENB Helper SE", 1, "T", version="1.6", nexus_id=23174),
            mod("SameMod", 2, "T", version="3.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "Source", "Target")

    def test_renamed_shows_target_first_with_source_alias(self):
        # Target name is primary; source name follows in a muted span.
        self.assertIn(
            'ENB Helper SE<span class="src-alias">(ENB Helper)</span>',
            self.html,
        )

    def test_renamed_whole_name_is_one_link(self):
        # Both names sit inside a single anchor to the source's Nexus page.
        self.assertIn(
            '<a href="https://www.nexusmods.com/skyrimspecialedition/mods/23174"'
            ' target="_blank" rel="noopener">'
            'ENB Helper SE<span class="src-alias">(ENB Helper)</span></a>',
            self.html,
        )

    def test_same_name_has_no_alias(self):
        self.assertIn(">SameMod</a>", self.html)
        # No alias span anywhere for SameMod.
        self.assertNotIn("(SameMod)", self.html)

    def test_add_shows_source_name_only(self):
        self.assertIn(">MissingMod</a>", self.html)
        self.assertNotIn("(MissingMod)", self.html)

    def test_src_alias_css_present(self):
        self.assertIn(".src-alias", self.html)
        # The source-name alias renders italic.
        self.assertIn("font-style: italic", self.html)

    def test_data_names_carries_both_names(self):
        self.assertIn('data-names="enb helper\nenb helper se"', self.html)

    def test_same_name_data_names_single(self):
        self.assertIn('data-names="samemod"', self.html)


class SummaryTest(unittest.TestCase):
    def test_counts(self):
        source = [
            sep("S", 0),
            mod("a", 1, "S", version="2.0", nexus_id=1),  # missing
            mod("b", 2, "S", version="2.0", nexus_id=2),  # common
        ]
        target = [sep("T", 0), mod("b", 1, "T", version="2.0", nexus_id=2)]
        rows = classify_source_mods(source, target)
        summary = compute_summary(rows)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["counts"][CoverageState.ADD], 1)
        self.assertEqual(summary["counts"][CoverageState.COMMON], 1)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0", nexus_id=99999),
            mod("OldMod", 3, "Combat", version="1.0", nexus_id=55555),
            mod("DiffMod", 4, "Combat", version="1.0beta", nexus_id=66666),
            sep("Done", 5),
            mod("SameMod", 6, "Done", version="3.0", nexus_id=11111),
        ]
        self.target = [
            sep("T", 0),
            mod("Valhalla Combat", 1, "T", version="1.4", nexus_id=64741),
            mod("OldMod", 2, "T", version="2.0", nexus_id=55555),
            mod("DiffMod", 3, "T", version="1.0alpha", nexus_id=66666),
            mod("SameMod", 4, "T", version="3.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "Source", "Target")

    def test_doctype_and_summary(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn("Source", self.html)
        self.assertIn("Target", self.html)

    def test_nexus_link_for_missing(self):
        self.assertIn(
            'href="https://www.nexusmods.com/skyrimspecialedition/mods/99999"',
            self.html,
        )

    def test_add_recolor(self):
        # "Missing" mods are reframed as green "to add" candidates (no red).
        self.assertIn("mod-add", self.html)
        self.assertIn("to add", self.html)
        self.assertNotIn("mod-missing", self.html)
        self.assertNotIn("stat-missing", self.html)

    def test_newer_direction_and_versions(self):
        # Target-first version display reads as an upgrade: your version -> candidate.
        self.assertIn("1.4 → 1.5", self.html)  # tgt -> src (cleaned)
        # The version string itself never uses an up-arrow; that glyph is the
        # NEWER row icon (asserted in test_state_icons), not part of the version.
        vers = re.findall(r'<span class="ver">(.*?)</span>', self.html)
        self.assertNotIn("↑", "".join(vers))

    def test_state_icons(self):
        # Each actionable state has a left-column glyph via a ::before rule,
        # driven by the row's state class; Common reserves the column but shows
        # no glyph. The same glyphs are mirrored on the summary badges.
        self.assertIn('.mod-add::before { content: "+";', self.html)
        self.assertIn('.mod-newer::before { content: "↑";', self.html)
        self.assertIn('.mod-differs::before { content: "≠";', self.html)
        self.assertIn('.mod-ignored::before { content: "⊘";', self.html)
        self.assertNotIn(".mod-common::before", self.html)
        self.assertIn('.stat-add::before { content: "+ ";', self.html)
        self.assertIn('.stat-newer::before { content: "↑ ";', self.html)
        self.assertIn('.stat-differs::before { content: "≠ ";', self.html)
        self.assertIn('.stat-ignored::before { content: "⊘ ";', self.html)

    def test_source_older_renders_as_common(self):
        # OldMod (src 1.0 < tgt 2.0) is now Common: no down-arrow anywhere,
        # and its row uses the common style, not a dedicated "older" style.
        self.assertNotIn("↓", self.html)
        self.assertNotIn("mod-older", self.html)

    def test_differs_glyph(self):
        self.assertIn("≠", self.html)                       # DIFFERS glyph
        self.assertIn("1.0beta ≠ 1.0alpha", self.html)      # src ≠ tgt (DiffMod)

    def test_hide_common_default_off(self):
        # The opening <body> tag must not carry the hide-common class at load.
        body_tag = re.search(r"<body[^>]*>", self.html).group()
        self.assertNotIn("hide-common", body_tag)

    def test_all_common_section_collapsed(self):
        # "Done" section has only SameMod (COMMON) -> collapsed by default.
        # Find each section *wrapper* div (not the section-header) and the block
        # of HTML until the next wrapper; the one holding "Done" must be collapsed.
        wrappers = list(re.finditer(r'<div class="(section(?: collapsed)?)">', self.html))
        self.assertTrue(wrappers)
        for i, m in enumerate(wrappers):
            start = m.end()
            end = wrappers[i + 1].start() if i + 1 < len(wrappers) else len(self.html)
            if "<span>Done</span>" in self.html[start:end]:
                self.assertIn("collapsed", m.group(1))
                break
        else:
            self.fail("Done section not found")

    def test_controls_present(self):
        self.assertIn("Hide common mods", self.html)
        self.assertIn("Expand all", self.html)
        self.assertIn("Collapse all", self.html)
        self.assertIn("function toggleCommon", self.html)

    def test_header_is_sticky(self):
        # The header carries the "Source: ... vs Target: ..." line and must stay
        # pinned to the top of the viewport while scrolling through long lists.
        match = re.search(r"\.header \{[^}]*\}", self.html)
        self.assertIsNotNone(match, "no .header CSS rule found")
        header_rule = match.group()
        self.assertIn("position: sticky", header_rule)
        self.assertIn("top: 0", header_rule)

    def test_section_headers_sticky(self):
        # Sub-section headers pin under the main header while scrolling.
        match = re.search(r"\.section-header \{[^}]*\}", self.html)
        self.assertIsNotNone(match, "no .section-header CSS rule found")
        rule = match.group()
        self.assertIn("position: sticky", rule)
        self.assertIn("var(--header-h", rule)
        # The offset variable is actually SET by JS (not just referenced in CSS),
        # measured from the main header's height and re-measured on resize.
        self.assertIn("--header-h", self.html)
        self.assertIn("setHeaderH", self.html)
        self.assertIn("offsetHeight", self.html)
        self.assertIn("resize", self.html)

    def test_filter_input_present(self):
        self.assertIn('id="filter-input"', self.html)
        self.assertIn('class="filter-input"', self.html)
        self.assertIn('type="search"', self.html)

    def test_filter_css_and_js(self):
        self.assertIn(".mod-row.filter-hidden", self.html)
        self.assertIn("function filterMods", self.html)
        self.assertIn("'Escape'", self.html)  # Esc clears the box

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

    def test_mod_rows_carry_data_names(self):
        # Every mod row exposes a lowercased name for the client filter.
        self.assertIn('data-names="valhalla combat"', self.html)


class MajorSectionTest(unittest.TestCase):
    def test_is_major_separator(self):
        from generate_coverage import is_major_separator, major_display_name
        self.assertTrue(is_major_separator("---------- BASE ----------"))
        self.assertTrue(is_major_separator("- - - GAMEPLAY CHANGES - - -"))
        self.assertFalse(is_major_separator("Core - SKSE Plugins & Fixes"))
        self.assertFalse(is_major_separator("21-9 WideScreen Support"))
        self.assertFalse(is_major_separator(""))
        self.assertEqual(major_display_name("---------- BASE ----------"), "BASE")
        self.assertEqual(
            major_display_name("- - - GAMEPLAY CHANGES - - -"), "GAMEPLAY CHANGES"
        )

    def test_band_emitted_per_major(self):
        from generate_coverage import (
            classify_source_mods,
            compute_summary,
            render_html,
            map_sections_to_majors,
        )
        source = [
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 0},
            {"type": "separator", "separatorName": "Base Game Cleaned", "order": 1},
            {"type": "mod", "modName": "Cleaned Masters", "order": 2,
             "separatorName": "Base Game Cleaned", "id": 1, "general": {"version": "1.0"}},
            {"type": "separator", "separatorName": "---------- USER INTERFACE ----------", "order": 3},
            {"type": "separator", "separatorName": "UI Stuff", "order": 4},
            {"type": "mod", "modName": "SkyUI", "order": 5,
             "separatorName": "UI Stuff", "id": 2, "general": {"version": "1.0"}},
        ]
        rows = classify_source_mods(source, [])
        summary = compute_summary(rows)
        majors = map_sections_to_majors(source)
        html = render_html(rows, summary, "S", "T", majors)
        self.assertIn('<div class="band">BASE</div>', html)
        self.assertIn('<div class="band">USER INTERFACE</div>', html)
        self.assertIn("Base Game Cleaned", html)
        self.assertIn("UI Stuff", html)

    def test_no_band_before_first_major(self):
        from generate_coverage import (
            classify_source_mods,
            compute_summary,
            render_html,
            map_sections_to_majors,
        )
        # Sections that appear before any major separator must emit NO band.
        source = [
            {"type": "separator", "separatorName": "Early Section", "order": 0},
            {"type": "mod", "modName": "EarlyMod", "separatorName": "Early Section",
             "order": 1, "id": 1, "general": {"version": "1.0"}},
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 2},
            {"type": "separator", "separatorName": "Base Stuff", "order": 3},
            {"type": "mod", "modName": "BaseMod", "separatorName": "Base Stuff",
             "order": 4, "id": 2, "general": {"version": "1.0"}},
        ]
        rows = classify_source_mods(source, [])
        majors = map_sections_to_majors(source)
        html = render_html(rows, compute_summary(rows), "S", "T", majors)
        # Exactly one band (BASE); the pre-major "Early Section" gets none.
        self.assertEqual(html.count('<div class="band">'), 1)
        self.assertIn('<div class="band">BASE</div>', html)
        self.assertIn("Early Section", html)  # still rendered, just bandless

    def test_mods_directly_under_major_render_bandless(self):
        from generate_coverage import (
            classify_source_mods,
            compute_summary,
            render_html,
            map_sections_to_majors,
        )
        # A mod whose separatorName IS the major separator renders directly under
        # the band, with no sub-header showing the raw dash-decorated name.
        source = [
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 0},
            {"type": "mod", "modName": "DirectMod", "separatorName": "---------- BASE ----------",
             "order": 1, "id": 1, "general": {"version": "1.0"}},
        ]
        rows = classify_source_mods(source, [])
        majors = map_sections_to_majors(source)
        html = render_html(rows, compute_summary(rows), "S", "T", majors)
        self.assertIn('<div class="band">BASE</div>', html)
        self.assertIn("DirectMod", html)
        # The raw decorated separator name is never shown as a header.
        self.assertNotIn("---------- BASE ----------", html)


class IgnoreTest(unittest.TestCase):
    def setUp(self):
        from coverage_ignore import IgnoreSet

        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5.0", nexus_id=64741),
            mod("MissingMod", 2, "Combat", version="2.0.0", nexus_id=99999),
        ]
        self.target = [
            sep("T", 0),
            mod("Valhalla Combat", 1, "T", version="1.5.0", nexus_id=64741),
        ]
        self.ignore = IgnoreSet(["MissingMod"])

    def _row(self, rows_by_section, name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def test_classify_sets_ignored(self):
        rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        self.assertTrue(self._row(rows, "MissingMod").ignored)
        self.assertFalse(self._row(rows, "Valhalla Combat").ignored)

    def test_default_no_ignore(self):
        rows = classify_source_mods(self.source, self.target)
        self.assertFalse(self._row(rows, "MissingMod").ignored)

    def test_summary_counts_ignored_separately(self):
        rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        summary = compute_summary(rows)
        self.assertEqual(summary["ignored"], 1)
        # MissingMod would be ADD, but ignored -> excluded from the add count.
        self.assertEqual(summary["counts"][CoverageState.ADD], 0)
        self.assertEqual(summary["total"], 2)


class RenderIgnoreTest(unittest.TestCase):
    def setUp(self):
        from coverage_ignore import IgnoreSet

        self.source = [
            sep("Combat", 0),
            mod("KeepMod", 1, "Combat", version="2.0", nexus_id=111),    # ADD
            mod("DropMod", 2, "Combat", version="2.0", nexus_id=222),    # ADD -> ignored
        ]
        self.target = [sep("T", 0)]
        self.ignore = IgnoreSet(["DropMod"])
        self.rows = classify_source_mods(self.source, self.target, ignore=self.ignore)
        self.summary = compute_summary(self.rows)

    def test_ignored_row_uses_muted_class(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn("mod-ignored", html)
        self.assertIn(".mod-ignored", html)

    def test_hide_common_covers_ignored(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn("body.hide-common .mod-ignored", html)

    def test_ignored_summary_stat(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn('id="stat-ignored"', html)
        self.assertIn("1 ignored", html)

    def test_ignored_excluded_from_section_badge(self):
        html = render_html(self.rows, self.summary, "S", "T")
        self.assertIn("1 add", html)
        self.assertNotIn("2 add", html)

    def test_serve_markup_only_when_serving(self):
        static = render_html(self.rows, self.summary, "S", "T")
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertNotIn("/api/ignore", static)
        self.assertNotIn("data-mod=", static)
        self.assertIn("data-names=", static)  # filter attr present even without serve
        self.assertIn("/api/ignore", served)
        self.assertIn("data-mod=", served)
        self.assertIn("data-state=", served)
        self.assertIn("data-ignored=", served)
        self.assertIn("data-names=", served)  # filter attr coexists with serve attrs
        self.assertIn('<body class="serve">', served)

    def test_serve_js_syncs_collapse(self):
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertIn("classList.toggle('collapsed'", served)


class FilterSectionVisibilityTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import map_sections_to_majors

        # A band (BASE) with one normal section under it plus a mod sitting
        # directly under the major (rendered bandless).
        self.source = [
            {"type": "separator", "separatorName": "---------- BASE ----------", "order": 0},
            {"type": "separator", "separatorName": "Base Stuff", "order": 1},
            {"type": "mod", "modName": "BaseMod", "separatorName": "Base Stuff",
             "order": 2, "id": 1, "general": {"version": "1.0"}},
            {"type": "mod", "modName": "DirectMod",
             "separatorName": "---------- BASE ----------",
             "order": 3, "id": 2, "general": {"version": "1.0"}},
        ]
        self.majors = map_sections_to_majors(self.source)
        self.rows = classify_source_mods(self.source, [])
        self.summary = compute_summary(self.rows)
        self.static = render_html(self.rows, self.summary, "S", "T", self.majors)
        self.served = render_html(
            self.rows, self.summary, "S", "T", self.majors, serve=True
        )

    def test_bandless_body_has_marker_class(self):
        # The standalone major body is tagged so the recompute/CSS can target it
        # without matching a normal section's inner body.
        self.assertIn('class="section-body bandless"', self.static)

    def test_filter_empty_css_rules_present(self):
        self.assertIn(".section.filter-empty", self.static)
        self.assertIn(".section-body.bandless.filter-empty", self.static)
        self.assertIn(".band.filter-empty", self.static)

    def test_section_visibility_js_present(self):
        self.assertIn("function applySectionVisibility", self.static)
        self.assertIn("function rowCounts", self.static)
        self.assertIn("function refilter", self.static)
        # filterMods drives the recompute (active iff there are filter terms).
        self.assertIn("applySectionVisibility(terms.length>0)", self.static)
        # Band visibility is decided by walking its sibling sections.
        self.assertIn("nextElementSibling", self.static)

    def test_rowcounts_accounts_for_hide_common(self):
        # A common/ignored row suppressed by Hide common must not keep its
        # section alive — the predicate checks both classes against hide-common.
        self.assertIn("hide-common", self.static)
        self.assertIn("mod-ignored", self.static)
        self.assertIn("mod-common", self.static)

    def test_toggle_common_refilters(self):
        self.assertIn("refilter();", self.static)

    def test_serve_refreshes_visibility_after_ignore(self):
        # Ignoring a mod can empty a section when Hide common is on, so the serve
        # ignore round-trip recounts AND refreshes section/band visibility.
        self.assertIn("recount();refilter();", self.served)


class CoveragePercentTest(unittest.TestCase):
    def test_all_common_is_full(self):
        self.assertEqual(coverage_percent(make_summary(4, common=4)), 100)

    def test_all_add_is_zero(self):
        self.assertEqual(coverage_percent(make_summary(4, add=4)), 0)

    def test_empty_is_none(self):
        # No mods -> undefined; render shows a dash instead of dividing by zero.
        self.assertIsNone(coverage_percent(make_summary(0)))

    def test_different_version_counts_half(self):
        # 2 common (1.0) + 2 newer (0.5 each) of 4 -> (2 + 1) / 4 = 75.
        self.assertEqual(coverage_percent(make_summary(4, newer=2, common=2)), 75)

    def test_differs_also_counts_half(self):
        # 1 common + 1 differs of 2 -> (1 + 0.5) / 2 = 75.
        self.assertEqual(coverage_percent(make_summary(2, differs=1, common=1)), 75)

    def test_ignored_counts_full(self):
        # Ignored is "handled" -> full weight, like common. 1 ignored + 1 add -> 50.
        self.assertEqual(coverage_percent(make_summary(2, add=1, ignored=1)), 50)

    def test_floors_down(self):
        # 1 common of 3 -> 33.33% floors to 33.
        self.assertEqual(coverage_percent(make_summary(3, add=2, common=1)), 33)

    def test_plugins_counts_half(self):
        # 1 common + 1 plugins of 2 -> (1 + 0.5) / 2 = 75.
        self.assertEqual(coverage_percent(make_summary(2, plugins=1, common=1)), 75)

    def test_removed_counts_zero(self):
        # 1 common + 1 removed of 2 -> (1 + 0) / 2 = 50.
        self.assertEqual(coverage_percent(make_summary(2, removed=1, common=1)), 50)


class RenderCoveragePercentTest(unittest.TestCase):
    def setUp(self):
        # 1 newer + 1 add + 2 common + 1 differs of 5 -> (2 + 0.5*2) / 5 = 60.
        self.source = [
            sep("Combat", 0),
            mod("Valhalla Combat", 1, "Combat", version="1.5", nexus_id=64741),  # newer
            mod("MissingMod", 2, "Combat", version="2.0", nexus_id=99999),       # add
            mod("OldMod", 3, "Combat", version="1.0", nexus_id=55555),           # common
            mod("DiffMod", 4, "Combat", version="1.0beta", nexus_id=66666),      # differs
            mod("SameMod", 5, "Combat", version="3.0", nexus_id=11111),          # common
        ]
        self.target = [
            sep("T", 0),
            mod("Valhalla Combat", 1, "T", version="1.4", nexus_id=64741),
            mod("OldMod", 2, "T", version="2.0", nexus_id=55555),
            mod("DiffMod", 3, "T", version="1.0alpha", nexus_id=66666),
            mod("SameMod", 4, "T", version="3.0", nexus_id=11111),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "Source", "Target")

    def test_badge_present_with_percent(self):
        self.assertIn('id="stat-covered"', self.html)
        self.assertIn("60% covered", self.html)

    def test_badge_has_tooltip_and_css(self):
        self.assertIn("stat-covered", self.html)  # both class and CSS rule
        self.assertIn('title="Share of source mods', self.html)

    def test_empty_renders_dash(self):
        html = render_html({}, make_summary(0), "S", "T")
        self.assertIn("— covered", html)

    def test_serve_recount_updates_covered(self):
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertIn("setStat('stat-covered'", served)


class PluginsStateTest(unittest.TestCase):
    def _row(self, rows_by_section, name):
        for rows in rows_by_section.values():
            for row in rows:
                if row.mod.get("modName") == name:
                    return row
        raise AssertionError(f"{name} not found")

    def _classify_pair(self, src_kwargs, tgt_kwargs):
        source = [sep("S", 0), mod("X", 1, "S", nexus_id=1, **src_kwargs)]
        target = [sep("T", 0), mod("X", 1, "T", nexus_id=1, **tgt_kwargs)]
        return self._row(classify_source_mods(source, target), "X")

    def test_same_version_different_plugins_is_plugins(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp", "B.esp"]},
            {"version": "1.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.PLUGINS)
        self.assertEqual(row.plugins_added, ("b.esp",))
        self.assertEqual(row.plugins_removed, ())

    def test_same_version_same_plugins_is_common(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp"]},
            {"version": "1.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_plugin_order_and_case_ignored(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["a.esp", "B.esp"]},
            {"version": "1.0", "plugins": ["B.ESP", "A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_unknown_version_with_plugin_diff_is_plugins(self):
        # Versions can't speak — plugin drift is the only usable signal.
        row = self._classify_pair(
            {"plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.PLUGINS)

    def test_unknown_version_same_plugins_stays_common(self):
        row = self._classify_pair(
            {"plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["A.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_source_older_with_plugin_diff_stays_common(self):
        # Target is ahead; matching an older source's layout isn't a goal.
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["A.esp"]},
            {"version": "2.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.COMMON)

    def test_newer_wins_over_plugin_diff(self):
        row = self._classify_pair(
            {"version": "2.0", "plugins": ["A.esp"]},
            {"version": "1.0", "plugins": ["B.esp"]},
        )
        self.assertEqual(row.state, CoverageState.NEWER)

    def test_delta_direction_is_what_target_would_change(self):
        row = self._classify_pair(
            {"version": "1.0", "plugins": ["C.esp"]},
            {"version": "1.0", "plugins": ["D.esp"]},
        )
        self.assertEqual(row.plugins_added, ("c.esp",))   # source has, target lacks
        self.assertEqual(row.plugins_removed, ("d.esp",))  # target has, source lacks


class PluginDeltaTextTest(unittest.TestCase):
    def _row(self, added=(), removed=()):
        from generate_coverage import CoverageRow
        row = CoverageRow({}, CoverageState.PLUGINS, "1.0", "1.0", None)
        row.plugins_added = tuple(added)
        row.plugins_removed = tuple(removed)
        return row

    def test_inline_up_to_three_names(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp",), removed=("b.esp",))
        self.assertEqual(_plugin_delta_text(row), "+a.esp −b.esp")

    def test_three_names_still_inline(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp"), removed=("c.esp",))
        self.assertEqual(_plugin_delta_text(row), "+a.esp +b.esp −c.esp")

    def test_four_or_more_collapse_to_counts(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp", "c.esp"), removed=("d.esp",))
        self.assertEqual(_plugin_delta_text(row), "+3 −1 plugins")

    def test_counts_omit_empty_side(self):
        from generate_coverage import _plugin_delta_text
        row = self._row(added=("a.esp", "b.esp", "c.esp", "d.esp"))
        self.assertEqual(_plugin_delta_text(row), "+4 plugins")


class RenderPluginsTest(unittest.TestCase):
    def setUp(self):
        self.source = [
            sep("S", 0),
            mod("PluginDrift", 1, "S", version="1.0", nexus_id=1,
                plugins=["A.esp", "B.esp"]),
            mod("Fine", 2, "S", version="1.0", nexus_id=2, plugins=["C.esp"]),
        ]
        self.target = [
            sep("T", 0),
            mod("PluginDrift", 1, "T", version="1.0", nexus_id=1,
                plugins=["A.esp"]),
            mod("Fine", 2, "T", version="1.0", nexus_id=2, plugins=["C.esp"]),
        ]
        self.rows = classify_source_mods(self.source, self.target)
        self.summary = compute_summary(self.rows)
        self.html = render_html(self.rows, self.summary, "S", "T")

    def test_row_class_and_glyphs_present(self):
        self.assertIn("mod-plugins", self.html)
        self.assertIn('.mod-plugins::before { content: "±";', self.html)
        self.assertIn('.stat-plugins::before { content: "± ";', self.html)

    def test_summary_badge(self):
        self.assertIn('id="stat-plugins"', self.html)
        self.assertIn("1 plugins", self.html)

    def test_inline_delta_and_tooltip(self):
        self.assertIn("+b.esp", self.html)
        self.assertIn('title="+b.esp"', self.html)

    def test_section_badge_counts_plugins(self):
        self.assertIn("1 plugins", self.html)
        self.assertNotIn("all present", self.html)

    def test_serve_recount_handles_plugins(self):
        served = render_html(self.rows, self.summary, "S", "T", serve=True)
        self.assertIn("c.plugins", served)
        self.assertIn("setStat('stat-plugins'", served)
        self.assertIn("'mod-plugins'", served)


class ComputeBaseChangesTest(unittest.TestCase):
    def _changes(self, base, source):
        from generate_coverage import compute_base_changes
        return compute_base_changes(base, source)

    def test_added_in_base(self):
        base = [sep("S", 0)]
        source = [sep("S", 0), mod("NewMod", 1, "S", version="1.0", nexus_id=1)]
        changed, removed = self._changes(base, source)
        self.assertEqual(len(changed), 1)
        self.assertEqual(list(changed.values()), ["New in base update"])
        self.assertEqual(removed, [])

    def test_version_change_flagged_with_note(self):
        base = [sep("S", 0), mod("Upd", 1, "S", version="1.2", nexus_id=1)]
        source = [sep("S", 0), mod("Upd", 1, "S", version="1.5", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(list(changed.values()), ["Base: 1.2 → 1.5"])

    def test_downgrade_counts_as_changed(self):
        base = [sep("S", 0), mod("Down", 1, "S", version="2.0", nexus_id=1)]
        source = [sep("S", 0), mod("Down", 1, "S", version="1.0", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(len(changed), 1)

    def test_unchanged_not_flagged(self):
        base = [sep("S", 0), mod("Same", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Same", 1, "S", version="1.0", nexus_id=1,
                                   plugins=["A.esp"])]
        changed, removed = self._changes(base, source)
        self.assertEqual(changed, {})
        self.assertEqual(removed, [])

    def test_unknown_version_pair_is_version_unchanged(self):
        # Per the classify_updates convention: either side Unknown -> no version change.
        base = [sep("S", 0), mod("NoVer", 1, "S", nexus_id=1)]
        source = [sep("S", 0), mod("NoVer", 1, "S", version="2.0", nexus_id=1)]
        changed, _ = self._changes(base, source)
        self.assertEqual(changed, {})

    def test_plugin_change_flagged_even_at_same_version(self):
        base = [sep("S", 0), mod("Plug", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Plug", 1, "S", version="1.0", nexus_id=1,
                                   plugins=["A.esp", "B.esp"])]
        changed, _ = self._changes(base, source)
        self.assertEqual(list(changed.values()), ["Base plugins: +b.esp"])

    def test_version_and_plugin_notes_combined(self):
        base = [sep("S", 0), mod("Both", 1, "S", version="1.0", nexus_id=1,
                                 plugins=["A.esp"])]
        source = [sep("S", 0), mod("Both", 1, "S", version="2.0", nexus_id=1,
                                   plugins=["B.esp"])]
        changed, _ = self._changes(base, source)
        self.assertEqual(
            list(changed.values()),
            ["Base: 1.0 → 2.0; Base plugins: +b.esp −a.esp"],
        )

    def test_removed_in_base_returned(self):
        base = [sep("S", 0), mod("Gone", 1, "S", version="1.0", nexus_id=1)]
        source = [sep("S", 0)]
        changed, removed = self._changes(base, source)
        self.assertEqual(changed, {})
        self.assertEqual([m["modName"] for m in removed], ["Gone"])


class BaseFilterTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import compute_base_changes
        self.base = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="1.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            sep("Quiet", 3),
            mod("AlsoStable", 4, "Quiet", version="1.0", nexus_id=3),
        ]
        self.source = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="2.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            sep("Quiet", 3),
            mod("AlsoStable", 4, "Quiet", version="1.0", nexus_id=3),
        ]
        self.target = [sep("T", 0)]
        self.base_changes, _ = compute_base_changes(self.base, self.source)

    def test_only_changed_mods_kept(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated"])

    def test_empty_sections_absent(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        self.assertEqual(list(rows.keys()), ["Combat"])  # "Quiet" gone

    def test_base_note_set_on_rows(self):
        rows = classify_source_mods(
            self.source, self.target, base_changes=self.base_changes
        )
        row = rows["Combat"][0]
        self.assertEqual(row.base_note, "Base: 1.0 → 2.0")

    def test_no_base_changes_means_no_filter_and_empty_note(self):
        rows = classify_source_mods(self.source, self.target)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated", "Stable", "AlsoStable"])
        self.assertEqual(rows["Combat"][0].base_note, "")


class RemovedStateTest(unittest.TestCase):
    def setUp(self):
        # Base mods that vanished from the new base (as returned by
        # compute_base_changes' removed list).
        self.removed_base_mods = [
            mod("StillHave", 0, "S", version="1.0", nexus_id=10),
            mod("NeverHad", 1, "S", version="1.0", nexus_id=11),
        ]
        self.target = [
            sep("T", 0),
            mod("StillHave", 1, "T", version="1.2", nexus_id=10),
        ]

    def test_only_target_present_mods_produce_rows(self):
        from generate_coverage import build_removed_rows
        rows = build_removed_rows(self.removed_base_mods, self.target)
        self.assertEqual([r.mod["modName"] for r in rows], ["StillHave"])

    def test_row_shape(self):
        from generate_coverage import build_removed_rows
        row = build_removed_rows(self.removed_base_mods, self.target)[0]
        self.assertEqual(row.state, CoverageState.REMOVED)
        self.assertEqual(row.nexus_id, 10)
        self.assertEqual(row.target_version, "1.2")
        self.assertEqual(row.target_name, "StillHave")

    def test_ignore_applies(self):
        from coverage_ignore import IgnoreSet
        from generate_coverage import build_removed_rows
        rows = build_removed_rows(
            self.removed_base_mods, self.target, ignore=IgnoreSet(["StillHave"])
        )
        self.assertTrue(rows[0].ignored)

    def test_empty_input_empty_output(self):
        from generate_coverage import build_removed_rows
        self.assertEqual(build_removed_rows([], self.target), [])


class RenderRemovedTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import build_removed_rows, REMOVED_SECTION
        removed_base_mods = [mod("GoneMod", 0, "S", version="1.0", nexus_id=10)]
        target = [sep("T", 0), mod("GoneMod", 1, "T", version="1.2", nexus_id=10)]
        rows = build_removed_rows(removed_base_mods, target)
        self.rows_by_section = {REMOVED_SECTION: rows}
        self.summary = compute_summary(self.rows_by_section)
        self.html = render_html(self.rows_by_section, self.summary, "S", "T")

    def test_removed_row_class_and_glyphs(self):
        self.assertIn("mod-removed", self.html)
        self.assertIn('.mod-removed::before { content: "−";', self.html)
        self.assertIn('.stat-removed::before { content: "− ";', self.html)

    def test_section_present_with_badge(self):
        self.assertIn("Removed in base update", self.html)
        self.assertIn("1 removed", self.html)

    def test_version_cell_shows_target_version(self):
        self.assertIn('<span class="ver">1.2</span>', self.html)

    def test_serve_recount_handles_removed(self):
        served = render_html(self.rows_by_section, self.summary, "S", "T", serve=True)
        self.assertIn("c.removed", served)
        self.assertIn("'mod-removed'", served)


class BuildReportTest(unittest.TestCase):
    def setUp(self):
        from generate_coverage import REMOVED_SECTION
        self.REMOVED_SECTION = REMOVED_SECTION
        self.base = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="1.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
            mod("GoneMod", 3, "Combat", version="1.0", nexus_id=3),
        ]
        self.source = [
            sep("Combat", 0),
            mod("Updated", 1, "Combat", version="2.0", nexus_id=1),
            mod("Stable", 2, "Combat", version="1.0", nexus_id=2),
        ]
        self.target = [
            sep("T", 0),
            mod("GoneMod", 1, "T", version="1.0", nexus_id=3),
        ]

    def test_without_base_matches_classify(self):
        from generate_coverage import build_report
        rows = build_report(self.source, self.target, 0.80, None)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["Updated", "Stable"])

    def test_with_base_filters_and_prepends_removed(self):
        from generate_coverage import build_report
        rows = build_report(self.source, self.target, 0.80, None,
                            base_data=self.base)
        # Removed section leads the report (most urgent), source sections follow.
        self.assertEqual(list(rows.keys()), [self.REMOVED_SECTION, "Combat"])
        self.assertEqual(
            [r.mod["modName"] for r in rows["Combat"]], ["Updated"]
        )
        self.assertEqual(
            [r.mod["modName"] for r in rows[self.REMOVED_SECTION]], ["GoneMod"]
        )

    def test_removed_section_absent_when_nothing_removed(self):
        from generate_coverage import build_report
        source_with_gone = self.source + [
            mod("GoneMod", 3, "Combat", version="1.0", nexus_id=3)
        ]
        rows = build_report(source_with_gone, self.target, 0.80, None,
                            base_data=self.base)
        self.assertNotIn(self.REMOVED_SECTION, rows)

    def test_replaced_mod_not_double_listed(self):
        # Base removed "Mod X" (page 30); the new base ships a renamed
        # successor "ModRebornX" (page 31) whose plugins claim the target's
        # "Mod X" (plugin-overlap match). Without the guard the same target
        # mod would get a Removed row (via its page-30 match to the removed
        # base mod) AND the successor's update row. The source claim wins:
        # no Removed section, just the successor row.
        from generate_coverage import build_report
        base = [
            sep("Combat", 0),
            mod("Mod X", 1, "Combat", version="1.0", nexus_id=30),
        ]
        source = [
            sep("Combat", 0),
            mod("ModRebornX", 1, "Combat", version="2.0", nexus_id=31,
                plugins=["x.esp"]),
        ]
        target = [
            sep("T", 0),
            mod("Mod X", 1, "T", version="1.0", nexus_id=30,
                plugins=["x.esp"]),
        ]
        rows = build_report(source, target, 0.80, None, base_data=base)
        self.assertNotIn(self.REMOVED_SECTION, rows)
        names = [r.mod["modName"] for rs in rows.values() for r in rs]
        self.assertEqual(names, ["ModRebornX"])

    def test_precomputed_match_is_honored(self):
        # An empty matched list means "no source mod claims any target mod":
        # every kept source mod must classify as Add, proving classify used
        # the caller's match instead of recomputing.
        rows = classify_source_mods(self.source, self.target, matched=[])
        states = {r.state for rs in rows.values() for r in rs}
        self.assertEqual(states, {CoverageState.ADD})


class RenderBaseModeTest(unittest.TestCase):
    def setUp(self):
        source = [sep("S", 0),
                  mod("NewMod", 1, "S", version="1.0", nexus_id=1)]
        self.rows = classify_source_mods(source, [sep("T", 0)])
        self.summary = compute_summary(self.rows)
        self.plain = render_html(self.rows, self.summary, "NewBase", "MyList")
        self.based = render_html(
            self.rows, self.summary, "NewBase", "MyList", base_name="OldBase"
        )

    def test_title_and_h1_switch(self):
        self.assertIn("<title>Base Update Coverage</title>", self.based)
        self.assertIn("<h1>Base Update Coverage</h1>", self.based)
        self.assertIn("<title>Modlist Coverage</title>", self.plain)
        self.assertIn("<h1>Modlist Coverage</h1>", self.plain)

    def test_lists_line_names_all_three(self):
        self.assertIn("Base update:", self.based)
        self.assertIn("OldBase", self.based)
        self.assertIn("applied to:", self.based)
        self.assertNotIn("Base update:", self.plain)

    def test_stat_removed_badge_only_in_base_mode(self):
        self.assertIn('id="stat-removed"', self.based)
        self.assertNotIn('id="stat-removed"', self.plain)

    def test_base_note_tooltip_rendered(self):
        row = next(iter(self.rows.values()))[0]
        row.base_note = "Base: 1.0 → 2.0"
        html = render_html(self.rows, self.summary, "NewBase", "MyList",
                           base_name="OldBase")
        self.assertIn('title="Base: 1.0 → 2.0"', html)

    def test_plugin_delta_and_base_note_join_in_tooltip(self):
        source = [sep("S", 0),
                  mod("Drift", 1, "S", version="1.0", nexus_id=2,
                      plugins=["A.esp", "B.esp"])]
        target = [sep("T", 0),
                  mod("Drift", 1, "T", version="1.0", nexus_id=2,
                      plugins=["A.esp"])]
        rows = classify_source_mods(source, target)
        row = rows["S"][0]
        row.base_note = "Base plugins: +b.esp"
        html = render_html(rows, compute_summary(rows), "NewBase", "MyList",
                           base_name="OldBase")
        self.assertIn('title="+b.esp | Base plugins: +b.esp"', html)


EXAMPLES_LISTS = os.path.join(os.path.dirname(__file__), "..", "examples", "lists")
EXAMPLES_REPORTS = os.path.join(os.path.dirname(__file__), "..", "examples", "reports")


class TestGenerateEntryPoint(unittest.TestCase):
    """generate() must reproduce the committed sample report byte-for-byte."""

    def test_generate_matches_committed_report(self):
        source = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.1.json"))
        target = load_modlist(os.path.join(EXAMPLES_LISTS, "Example List 1.0.json"))
        ignore = load_ignore(
            os.path.join(EXAMPLES_REPORTS, "Example List 1.0", ".coverage-ignore.txt")
        )
        html = generate_coverage.generate(
            source, target, "Example List 1.1", "Example List 1.0", ignore=ignore
        )
        committed = os.path.join(
            EXAMPLES_REPORTS, "Example List 1.0", "Example List 1.1.coverage.html"
        )
        with open(committed, "r", encoding="utf-8", newline="") as f:
            self.assertEqual(html, f.read())


_PROGRESS_LISTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "examples", "lists"
)


class GenerateProgressTest(unittest.TestCase):
    def _load(self, name):
        from modlist_utils import load_modlist
        return load_modlist(os.path.join(_PROGRESS_LISTS, name))

    def test_generate_forwards_progress(self):
        calls = []
        old = self._load("Example List 1.0.json")
        new = self._load("Example List 1.1.json")
        generate_coverage.generate(
            old, new, "Src", "Tgt", progress=lambda d, t: calls.append((d, t))
        )
        self.assertTrue(calls)
        done, total = calls[-1]
        self.assertGreater(total, 0)
        self.assertEqual(done, total)


if __name__ == "__main__":
    unittest.main()
