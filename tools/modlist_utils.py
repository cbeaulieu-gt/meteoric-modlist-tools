"""
Shared utilities for modlist comparison tools.

Provides data loading, mod matching, version cleaning, and name normalization
functions used by both generate_changelog.py and generate_diff.py.
"""

import difflib
import json
import os
import re


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_modlist(file_path):
    """Load a JSON modlist file and return the raw array of items."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_output_path(output_arg, first_path, second_path, type_label, ext,
                        first_name=None):
    """Resolve the final output file path for a generated report.

    - output_arg is falsy (None/"")  -> return None (caller writes to stdout).
    - output_arg names a directory   -> return
        <output_arg>/<basename(second_path)>/<basename(first_path)>.<type_label>.<ext>
      creating intermediate directories. "Directory" means it ends with a path
      separator or is an existing directory. The folder is named after the SECOND
      positional list, the file after the FIRST.
    - otherwise                      -> return output_arg unchanged (explicit file).

    Names derive from the input *filenames*, which already exist on disk and are
    therefore filesystem-safe.

    first_name overrides the filename stem derived from first_path (the type/ext
    convention is unchanged) — used by rebase reports, whose stem decorates the
    source name with the base list.
    """
    if not output_arg:
        return None

    is_dir = output_arg.endswith(("/", "\\")) or os.path.isdir(output_arg)
    if not is_dir:
        return output_arg

    folder = os.path.splitext(os.path.basename(second_path))[0]
    name = first_name or os.path.splitext(os.path.basename(first_path))[0]
    target_dir = os.path.join(output_arg, folder)
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, f"{name}.{type_label}.{ext}")


def extract_mods(modlist_data):
    """Filter to only mod items (exclude separators)."""
    return [item for item in modlist_data if item.get("type") == "mod"]


def plugin_set(mod):
    """Normalized plugin-filename set for cross-list comparison.

    Plugins are compared as filenames only: lowercased, whitespace-trimmed,
    order-independent. Blank entries are dropped; a mod without plugins yields
    an empty frozenset (and two empty sets compare equal).
    """
    return frozenset(
        p.strip().lower() for p in mod.get("plugins", []) if p and p.strip()
    )


def name_key(name):
    """Identity key for an MO2 name (mod or separator).

    MO2 itself is case-insensitive about mod and separator names — a list cannot
    hold both "Core" and "CORE" — so any equality test between two names must go
    through this. Casefolds and trims; unlike :func:`normalize_name` it strips
    nothing else, so it stays safe for grouping and dict keys.
    """
    return (name or "").strip().casefold()


def same_name(a, b):
    """True when two MO2 names refer to the same thing (see :func:`name_key`)."""
    return name_key(a) == name_key(b)


def get_separator_order(modlist_data):
    """Extract separator names in their order of appearance.

    Names differing only in case are the same separator to MO2, so the first
    spelling seen wins.
    """
    seen = set()
    order = []
    for item in modlist_data:
        if item.get("type") == "separator":
            name = item.get("separatorName", "")
            key = name_key(name)
            if name and key not in seen:
                seen.add(key)
                order.append(name)
    return order


def is_major_separator(name):
    """A 'major' separator is one whose name is wrapped in dashes, e.g.
    '---------- BASE ----------' or '- - - GAMEPLAY CHANGES - - -'. It denotes an
    implicit top-level grouping in MO2's otherwise-flat separator list."""
    s = (name or "").strip()
    return len(s) >= 2 and s[0] == "-" and s[-1] == "-" and any(c.isalnum() for c in s)


def major_display_name(name):
    """Strip surrounding dash/space decoration: '---------- BASE ----------' -> 'BASE'."""
    return (name or "").strip().strip("- ").strip()


NEXUS_URL = "https://www.nexusmods.com/skyrimspecialedition/mods/{id}"


def nexus_url(mod):
    """Nexus page URL for a mod, or None if it has no numeric page id.

    A Nexus ``id`` is the page id; a non-int id (typically None, as on
    separators or hand-added mods) has no linkable page.
    """
    raw_id = mod.get("id")
    return NEXUS_URL.format(id=raw_id) if isinstance(raw_id, int) else None


# ---------------------------------------------------------------------------
# Version Cleaning
# ---------------------------------------------------------------------------

def clean_version(raw):
    """
    Convert a raw meta.ini version string to MO2 displayString format.

    Examples:
        "4.3.3.0"    -> "4.3.3"
        "4.3.6.0c"   -> "4.3.6c"
        "1.7.0.0b"   -> "1.7beta"
        "4.1.2.0b-"  -> "4.1.2beta-"
        "d2025.7.31.0" -> "7/31/2025"
        "f5.06"      -> "5.06"
        "MCM-01"     -> "MCM-01"
        ""           -> "Unknown"
    """
    if not raw or not raw.strip():
        return "Unknown"

    raw = raw.strip()

    # Date format: dYYYY.M.D[.0]
    date_match = re.match(r"^d(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.0)?$", raw)
    if date_match:
        year, month, day = date_match.groups()
        return f"{int(month)}/{int(day)}/{year}"

    # File version format: fX.YY...
    if re.match(r"^f\d", raw):
        return raw[1:]

    # Standard numeric versions with possible letter suffix
    # Match: digits and dots, optionally followed by letter(s) and more chars
    std_match = re.match(r"^(\d+(?:\.\d+)*)(\.\d+)*(\.\d+)?([a-zA-Z].*)$", raw)
    if std_match:
        # Has a letter suffix after the numeric part
        # We need to handle trailing .0 segments before the suffix
        # Re-parse more carefully
        pass

    # General approach: split into numeric part and suffix
    # Find where the letters start after the version digits
    m = re.match(r"^(\d+(?:\.\d+)*)((?:[a-zA-Z].*)?)$", raw)
    if m:
        numeric_part = m.group(1)
        suffix = m.group(2)

        # Strip trailing .0 segments from numeric part
        # But keep at least major.minor
        parts = numeric_part.split(".")
        while len(parts) > 2 and parts[-1] == "0":
            parts.pop()

        cleaned_numeric = ".".join(parts)

        # Convert lone 'b' suffix to 'beta' (MO2 convention)
        # 'b' followed by nothing or '-' means beta
        if suffix and re.match(r"^b(-?)$", suffix):
            suffix = "beta" + suffix[1:]

        return cleaned_numeric + suffix

    # Non-standard version (e.g., "MCM-01", "Alpha-58") — keep as-is
    return raw


def get_version(mod):
    """Extract and clean the version from a mod dict."""
    general = mod.get("general", {})
    if not general:
        return "Unknown"
    raw = general.get("version", "")
    return clean_version(raw)


# ---------------------------------------------------------------------------
# Version Comparison
# ---------------------------------------------------------------------------

def _parse_version_for_compare(v):
    """
    Parse an already-cleaned version string into a comparable representation.

    Returns:
        ("date", (year, month, day))  for M/D/YYYY dates
        ("num", (int, int, ...))      for a leading numeric dotted sequence
        None                          when no numeric/date part is parseable
    """
    if not v or v == "Unknown":
        return None
    v = v.strip()

    # Date form produced by clean_version: M/D/YYYY
    date_match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if date_match:
        month, day, year = (int(x) for x in date_match.groups())
        return ("date", (year, month, day))

    # Leading numeric dotted sequence, e.g. "4.3.6c" -> (4, 3, 6)
    num_match = re.match(r"^(\d+(?:\.\d+)*)", v)
    if num_match:
        nums = tuple(int(x) for x in num_match.group(1).split("."))
        return ("num", nums)

    return None


def compare_versions(a, b):
    """
    Best-effort comparison of two already-cleaned version strings.

    Returns:
        -1  if a < b
         0  if a == b
         1  if a > b
       None if the versions differ but the direction can't be determined
            (e.g. equal numeric parts with differing suffixes, non-numeric
            strings, or a date compared against a numeric version).
    """
    if a == b:
        return 0

    pa = _parse_version_for_compare(a)
    pb = _parse_version_for_compare(b)
    if pa is None or pb is None:
        return None

    kind_a, val_a = pa
    kind_b, val_b = pb
    if kind_a != kind_b:
        return None  # date vs numeric — not comparable

    if kind_a == "date":
        if val_a < val_b:
            return -1
        if val_a > val_b:
            return 1
        return None  # same date but original strings differed

    # numeric: zero-pad to equal length, then compare
    la, lb = list(val_a), list(val_b)
    n = max(len(la), len(lb))
    la += [0] * (n - len(la))
    lb += [0] * (n - len(lb))
    if la < lb:
        return -1
    if la > lb:
        return 1
    # Numeric parts are equal after zero-padding.
    # Check whether the original strings differ only by trailing zeros (e.g. "1.2" vs "1.2.0").
    # If so, they are semantically identical → 0.
    # If the strings differ for another reason (e.g. "1.7" vs "1.7beta"), the num_match only
    # captured the leading digits, so the full strings still differ → None.
    def strip_trailing_zero_segments(s):
        parts = s.split(".")
        while len(parts) > 1 and parts[-1] == "0":
            parts.pop()
        return ".".join(parts)

    if strip_trailing_zero_segments(a) == strip_trailing_zero_segments(b):
        return 0
    return None  # numeric parts equal but full strings differ (e.g. "1.7" vs "1.7beta")


# ---------------------------------------------------------------------------
# Nexus Archive Filename Parsing (version recovery + identity)
# ---------------------------------------------------------------------------

# A trailing Unix-epoch timestamp (>= 9 digits; real ones are 10). When present
# it is peeled off; when absent the whole tail after the modid is the version
# (older / manually-named files carry no timestamp).
_EPOCH_RE = re.compile(r"^(?P<version>.+)-(?P<epoch>\d{9,})$")
_EPOCH_ONLY_RE = re.compile(r"^\d{9,}$")
# A digit-leading version: dot-separated alphanumeric segments (no empty/trailing
# segments). Here the filename's dashes are encoded dots and get converted.
_VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z]*(?:\.[0-9A-Za-z]+)*$")
# A word-leading version tag (e.g. 'Alpha-41', 'MCM-01'): kept verbatim (its
# dashes are real separators, not encoded dots). Accepted only when it contains
# a digit, which rejects stray name fragments like 'fs'.
_WORD_VERSION_RE = re.compile(r"^[A-Za-z][0-9A-Za-z.\-]*$")


def _normalize_recovered(version_raw):
    """Turn the raw between-modid-and-epoch token into a version, or None.

    Digit-leading tokens are numeric versions whose dashes are encoded dots, so
    they are converted ('1-2-0a' -> '1.2.0a') and validated. Word-leading tokens
    are real tags ('Alpha-41', 'MCM-01'): kept verbatim, accepted only if they
    contain a digit. Everything else is rejected.
    """
    if not version_raw:
        return None
    if version_raw[:1].isdigit():
        version = version_raw.replace("-", ".")
        return version if _VERSION_RE.match(version) else None
    if any(ch.isdigit() for ch in version_raw) and _WORD_VERSION_RE.match(version_raw):
        return version_raw
    return None


def recover_version(installation_file, modid):
    """Recover a mod's version from its Nexus installationFile name, or None.

    Nexus download names look like:
        <name>-<modid>-<version>[-<epoch>].<ext>
    where the version's dots are rendered as dashes and the optional epoch is the
    file's Unix timestamp. Using the known modid as a structural anchor, this
    returns the version, or None when the name does not confidently yield one.

    Confidence gates:
      - modid must appear as '-<modid>-' in the name (rightmost match anchors,
        so a modid-like substring earlier in the name cannot mislead).
      - if a trailing '-<digits>' epoch of >= 9 digits is present it is peeled
        off; otherwise the whole tail is the version. A tail that is *only* an
        epoch (no version) yields None.
      - a leading 'v'/'V' before a digit is dropped ('-v2-2-1-' -> '2.2.1').
      - the result must be a digit-leading numeric version or a word tag that
        contains a digit (see _normalize_recovered).
    """
    if not installation_file or not modid:
        return None
    stem = os.path.splitext(installation_file)[0]
    marker = f"-{modid}-"
    anchor = stem.rfind(marker)
    if anchor == -1:
        return None
    tail = stem[anchor + len(marker):]
    epoch_match = _EPOCH_RE.match(tail)
    if epoch_match:
        version_raw = epoch_match.group("version")
    elif _EPOCH_ONLY_RE.match(tail):
        return None  # tail is just an epoch — no version present
    else:
        version_raw = tail
    # Nexus often prefixes the version with 'v' (e.g. '-v2-2-1-'); drop a leading
    # v/V when it sits directly before a digit so the rest can validate.
    if version_raw[:1] in ("v", "V") and version_raw[1:2].isdigit():
        version_raw = version_raw[1:]
    return _normalize_recovered(version_raw)


def parse_archive_identity(filename, modid):
    """Return (name_stem, version) parsed from a Nexus archive filename.

    The name is anchored on the literal '-<modid>-' substring (rightmost match,
    mirroring recover_version). name_stem is the portion *before* that anchor,
    normalized: lowercased, a leading 'NN_' MO2 rename prefix stripped,
    surrounding whitespace trimmed, internal whitespace runs collapsed to a
    single space (punctuation preserved, so '(16-9) (2K)' and '(21-9) (4K)'
    stay distinct). version is recover_version's result. Either element is None
    when that part cannot be confidently parsed: anchor absent -> (None, None);
    version tail only an epoch -> (name_stem, None).
    """
    if not filename or not modid:
        return (None, None)
    stem = os.path.splitext(filename)[0]
    anchor = stem.rfind(f"-{modid}-")
    if anchor == -1:
        return (None, None)
    name_part = re.sub(r"^\d+_", "", stem[:anchor].strip().lower())
    name_stem = re.sub(r"\s+", " ", name_part).strip()
    return (name_stem or None, recover_version(filename, modid))


# ---------------------------------------------------------------------------
# Name Normalization
# ---------------------------------------------------------------------------

SUFFIX_PATTERNS = [
    r"\s*-?\s*sse$",
    r"\s*-?\s*se$",
    r"\s*-?\s*ae$",
    r"\s*-?\s*flm$",
    r"\s*-?\s*wabbajack$",
    r"\s+v?\d+(\.\d+)*$",  # version numbers like "v1.2.3" or "1.2.3"
]


def normalize_name(name):
    """
    Standard normalization: lowercase, strip common suffixes.
    Preserves 'NG' as it indicates a different mod version.
    """
    name = name.lower().strip()
    for pattern in SUFFIX_PATTERNS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
    return name.strip()


def normalize_name_strict(name):
    """
    Aggressive normalization: standard + strip all non-alphanumeric.
    e.g. "Phoenix - Compendium SSE" -> "phoenixcompendium"
    """
    name = normalize_name(name)
    return re.sub(r"[^a-z0-9]", "", name)


# ---------------------------------------------------------------------------
# Mod Matching
# ---------------------------------------------------------------------------

def _norm_install_file(name):
    """
    Normalize an installationFile (Nexus archive) name for equality comparison.

    Lowercases and strips a leading numeric rename prefix that MO2 can prepend
    to disambiguate duplicate archive names (e.g. "1_Mod-123-1-0-...zip").
    The archive name is otherwise compared whole — its internal version/timestamp
    structure is variable, so it is never parsed.
    """
    if not name:
        return ""
    return re.sub(r"^\d+_", "", name.strip().lower())


def _file_identity_keys(mod):
    """
    File-level identity keys for a mod, most-specific first.

    A Nexus ``id`` identifies a *page*, which can host many distinct mods; these
    keys identify the actual *file*. Returns ``("fid", modid, fileid)`` keys for
    each installed fileid, followed by an ``("inst", modid, archive)`` key for the
    installationFile. Empty when the mod has no numeric id, or neither a fileid
    nor an installationFile.
    """
    mod_id = mod.get("id")
    if not isinstance(mod_id, int):
        return []
    keys = []
    for f in mod.get("installed", {}).get("files", []):
        fid = f.get("fileid")
        if fid:
            keys.append(("fid", mod_id, str(fid)))
    inst = _norm_install_file(mod.get("general", {}).get("installationFile", ""))
    if inst:
        keys.append(("inst", mod_id, inst))
    return keys


def _match_by_plugins(old_mod, candidates):
    """Try to match by plugin overlap. Returns (matched_mod, confidence) or None."""
    old_plugins = set(p.lower() for p in old_mod.get("plugins", []))
    if not old_plugins:
        return None

    best_match = None
    best_confidence = 0.0

    for new_mod in candidates:
        new_plugins = set(p.lower() for p in new_mod.get("plugins", []))
        if not new_plugins:
            continue

        # Exact set match
        if old_plugins == new_plugins:
            return (new_mod, 0.90)

        # Overlap match
        overlap = old_plugins & new_plugins
        if overlap:
            # Overlap relative to the smaller set
            smaller = min(len(old_plugins), len(new_plugins))
            ratio = len(overlap) / smaller
            if ratio >= 0.5 and ratio > best_confidence:
                best_confidence = ratio * 0.85
                best_match = new_mod

    if best_match and best_confidence >= 0.50:
        return (best_match, best_confidence)
    return None


def _match_by_name(old_mod, candidates_by_strict_name, candidates, min_confidence):
    """
    Try to match by name. First strict normalization, then fuzzy.
    Returns (matched_mod, confidence) or None.
    """
    old_name = old_mod.get("modName", "")
    if not old_name:
        return None

    old_strict = normalize_name_strict(old_name)

    # Strict name match
    if old_strict and old_strict in candidates_by_strict_name:
        return (candidates_by_strict_name[old_strict], 0.95)

    # Fuzzy name match
    old_normalized = normalize_name(old_name)
    best_match = None
    best_ratio = 0.0

    for new_mod in candidates:
        new_name = new_mod.get("modName", "")
        if not new_name:
            continue
        new_normalized = normalize_name(new_name)
        ratio = difflib.SequenceMatcher(None, old_normalized, new_normalized).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = new_mod

    if best_match and best_ratio >= min_confidence:
        return (best_match, best_ratio)
    return None


def match_mods(old_mods, new_mods, min_confidence=0.80):
    """
    Match mods between old and new lists using waterfall strategy.
    Returns (matched_pairs, added_mods, removed_mods).
    """
    matched = []  # list of (old_mod, new_mod)
    matched_new_ids = set()  # track which new mods have been matched (by index)

    # Build lookup structures for new mods
    new_mods_by_nexus_id = {}  # nexus page id -> list of mods (a page hosts many mods)
    new_mod_indices = {}  # mod id(obj) -> index in new_mods
    for i, mod in enumerate(new_mods):
        new_mod_indices[id(mod)] = i
        mod_id = mod.get("id")
        if isinstance(mod_id, int):
            new_mods_by_nexus_id.setdefault(mod_id, []).append(mod)

    # A page id is "ambiguous" when more than one mod in either list carries it —
    # the signal that the id is page-level, not file-level, so the id alone can't
    # identify the mod and a name (or file-identity) must corroborate.
    def _count_ids(mods):
        counts = {}
        for m in mods:
            mid = m.get("id")
            if isinstance(mid, int):
                counts[mid] = counts.get(mid, 0) + 1
        return counts

    old_id_counts = _count_ids(old_mods)
    new_id_counts = _count_ids(new_mods)

    def get_unmatched_new():
        return [m for i, m in enumerate(new_mods) if i not in matched_new_ids]

    def mark_matched(old_mod, new_mod):
        matched.append((old_mod, new_mod))
        idx = new_mod_indices[id(new_mod)]
        matched_new_ids.add(idx)

    # Build strict-name index for unmatched new mods (rebuilt after each phase)
    def build_strict_name_index(candidates):
        index = {}
        for mod in candidates:
            name = mod.get("modName", "")
            if name:
                strict = normalize_name_strict(name)
                if strict and strict not in index:
                    index[strict] = mod
        return index

    def pair_score(old_mod, new_mod, unique_page):
        """Strength of evidence that old_mod and new_mod are the same mod, within a
        shared Nexus page. Higher wins. The ordering is deliberate: a shared fileid
        (same upload) beats an exact name, which beats a shared archive name, which
        beats a fuzzy name. This stops a greedy file-identity match from stealing a
        target that an exact-name pair should own. Returns a positive score for an
        acceptable match, else -1.
        """
        shared = set(_file_identity_keys(old_mod)) & set(_file_identity_keys(new_mod))
        if any(k[0] == "fid" for k in shared):
            return 100.0
        old_strict = normalize_name_strict(old_mod.get("modName", ""))
        if old_strict and old_strict == normalize_name_strict(new_mod.get("modName", "")):
            return 50.0
        if any(k[0] == "inst" for k in shared):
            return 40.0
        ratio = difflib.SequenceMatcher(
            None, normalize_name(old_mod.get("modName", "")),
            normalize_name(new_mod.get("modName", "")),
        ).ratio()
        if ratio >= min_confidence:
            return 10.0 + ratio
        # A page that hosts a single mod in each list matches blindly, so a plain
        # rename (no fileid/archive/name signal) is still recognized.
        if unique_page:
            return 1.0
        return -1.0

    # Phase 1: per-page (Nexus id) assignment. For each page id, score every
    # source/target pair and assign greedily from the strongest evidence down, so a
    # weaker signal can never claim a target that a stronger pairing wants.
    src_by_id = {}
    for old_mod in old_mods:
        oid = old_mod.get("id")
        if isinstance(oid, int):
            src_by_id.setdefault(oid, []).append(old_mod)

    matched_old_ids = set()
    for old_id, src_group in src_by_id.items():
        tgt_group = new_mods_by_nexus_id.get(old_id, [])
        if not tgt_group:
            continue
        unique_page = old_id_counts.get(old_id, 0) == 1 and new_id_counts.get(old_id, 0) == 1
        scored = []
        for s in src_group:
            for t in tgt_group:
                score = pair_score(s, t, unique_page)
                if score > 0:
                    scored.append((score, s, t))
        scored.sort(key=lambda p: p[0], reverse=True)
        for score, s, t in scored:
            if id(s) in matched_old_ids:
                continue
            if new_mod_indices[id(t)] in matched_new_ids:
                continue
            mark_matched(s, t)
            matched_old_ids.add(id(s))

    unmatched_old = [m for m in old_mods if id(m) not in matched_old_ids]

    # Phase 2: Plugin-based matching
    still_unmatched_old = []
    for old_mod in unmatched_old:
        candidates = get_unmatched_new()
        result = _match_by_plugins(old_mod, candidates)
        if result:
            mark_matched(old_mod, result[0])
        else:
            still_unmatched_old.append(old_mod)
    unmatched_old = still_unmatched_old

    # Phase 3: Name-based matching (strict then fuzzy)
    still_unmatched_old = []
    for old_mod in unmatched_old:
        candidates = get_unmatched_new()
        strict_index = build_strict_name_index(candidates)
        result = _match_by_name(old_mod, strict_index, candidates, min_confidence)
        if result:
            mark_matched(old_mod, result[0])
        else:
            still_unmatched_old.append(old_mod)

    # Remaining: unmatched old = removed, unmatched new = added
    removed = still_unmatched_old
    added = get_unmatched_new()

    return matched, added, removed


# ---------------------------------------------------------------------------
# Change Classification
# ---------------------------------------------------------------------------

def classify_updates(matched_pairs):
    """
    From matched pairs, find mods with version changes.
    Only includes mods where BOTH versions are known (non-empty, non-Unknown).
    Returns list of (mod_name, old_version, new_version).
    """
    updated = []
    for old_mod, new_mod in matched_pairs:
        old_ver = get_version(old_mod)
        new_ver = get_version(new_mod)

        # Skip if either version is unknown
        if old_ver == "Unknown" or new_ver == "Unknown":
            continue

        if old_ver != new_ver:
            display_name = new_mod.get("modName", old_mod.get("modName", "Unknown"))
            updated.append((display_name, old_ver, new_ver))

    updated.sort(key=lambda x: x[0].lower())
    return updated
