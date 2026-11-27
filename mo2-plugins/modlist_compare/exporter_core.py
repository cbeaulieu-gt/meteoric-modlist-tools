"""Core modlist-export logic shared by both Modlist Compare tools.

Pure helpers live at module level and are unit-tested outside MO2; only
export_modlist touches mobase (imported lazily inside the function).
"""
import configparser
import os
import re


def strip_tags(mod_name):
    """Remove all [tags] from the beginning of a mod name."""
    pattern = r'^(\[[^\]]+\]\s*)+\s*'
    return re.sub(pattern, '', mod_name).strip()


def extract_tags(mod_name):
    """Extract all [tag] values from a mod name."""
    return re.findall(r'\[([^\]]+)\]', mod_name)


def sanitize_filename(filename):
    """Replace filesystem-unsafe characters; empty input falls back."""
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    filename = filename.strip('. ')
    return filename if filename else "modlist_export"


def get_plugin_files(mod_path):
    """Sorted plugin filenames (.esp/.esl/.esm) directly inside mod_path."""
    plugins = []
    if not os.path.exists(mod_path):
        return plugins
    try:
        for file in os.listdir(mod_path):
            if file.lower().endswith(('.esp', '.esl', '.esm')):
                plugins.append(file)
    except Exception:
        pass
    return sorted(plugins)


def read_meta_ini(mod_path):
    """Read meta.ini's [General] and [installedFiles] sections."""
    general_data = {}
    installed_files_data = {}
    meta_ini_path = os.path.join(mod_path, "meta.ini")
    if not os.path.exists(meta_ini_path):
        return general_data, installed_files_data
    try:
        config = configparser.ConfigParser()
        config.read(meta_ini_path, encoding='utf-8')
        if 'General' in config:
            section = config['General']
            general_data = {
                'modid': section.get('modid', ''),
                'version': section.get('version', ''),
                'newestVersion': section.get('newestVersion', ''),
                'category': section.get('category', ''),
                'installationFile': section.get('installationFile', ''),
            }
        if 'installedFiles' in config:
            section = config['installedFiles']
            size = int(section.get('size', 0))
            installed_files_data['size'] = size
            installed_files_data['files'] = []
            for i in range(1, size + 1):
                installed_files_data['files'].append({
                    'modid': section.get(f'{i}\\modid', ''),
                    'fileid': section.get(f'{i}\\fileid', ''),
                })
    except Exception:
        pass
    return general_data, installed_files_data


def suggested_list_name(organizer):
    """First separator's cleaned name (sanitized), or 'modlist_export'."""
    mod_list = organizer.modList()
    for mod_name in list(mod_list.allModsByProfilePriority()):
        mod = organizer.getMod(mod_name)
        if mod and (mod.isSeparator() or mod_name.endswith('_separator')):
            name = strip_tags(mod_name).replace("_separator", "").strip()
            return sanitize_filename(name)
    return "modlist_export"


def make_separator_item(mod_name, order):
    """Build the item dict for a separator entry."""
    separator_name = strip_tags(mod_name).replace("_separator", "").strip()
    return {
        "id": None,
        "type": "separator",
        "separatorName": separator_name,
        "modName": separator_name,
        "displayName": mod_name,
        "plugins": [],
        "general": {},
        "installed": {},
        "order": order,
        "tags": extract_tags(mod_name),
        "active": True,
    }


def make_mod_item(mod_name, current_separator, nexus_id, mod_path, active, order):
    """Build the item dict for a mod entry."""
    clean_mod_name = strip_tags(mod_name)
    general_data, installed_files_data = read_meta_ini(mod_path)
    return {
        "id": nexus_id if nexus_id > 0 else clean_mod_name,
        "type": "mod",
        "separatorName": current_separator,
        "modName": clean_mod_name,
        "displayName": mod_name,
        "plugins": get_plugin_files(mod_path),
        "general": general_data,
        "installed": installed_files_data,
        "order": order,
        "tags": extract_tags(mod_name),
        "active": active,
    }


def export_modlist(organizer):
    """Export the active modlist as the JSON-ready list of item dicts.

    Same structure as FORMAT_SPECIFICATION.md; order follows
    allModsByProfilePriority (top-to-bottom).
    """
    import mobase

    modlist_data = []
    mod_list = organizer.modList()
    current_separator = "Unsectioned"

    for mod_name in list(mod_list.allModsByProfilePriority()):
        mod = organizer.getMod(mod_name)
        if not mod:
            continue

        if mod.isSeparator() or mod_name.endswith('_separator'):
            item = make_separator_item(mod_name, len(modlist_data))
            current_separator = item["separatorName"]
            modlist_data.append(item)
            continue

        is_active = mod_list.state(mod_name) & mobase.ModState.ACTIVE != 0
        modlist_data.append(make_mod_item(
            mod_name, current_separator, mod.nexusId(), mod.absolutePath(),
            is_active, len(modlist_data),
        ))

    for idx, item in enumerate(modlist_data):
        item["order"] = idx
    return modlist_data


def parse_modlist_txt(text):
    """Parse modlist.txt into (name, enabled) pairs, file order.

    The file lists highest priority first. '+' is enabled, '-' disabled;
    '*' (unmanaged), '#' comments and blank lines are skipped.
    """
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] not in "+-":
            continue
        entries.append((line[1:], line[0] == "+"))
    return entries


def _modid_from_meta(mod_path):
    """Nexus id from meta.ini, or 0 when absent, blank or invalid."""
    general, _ = read_meta_ini(mod_path)
    try:
        return int(general.get("modid", "") or 0)
    except ValueError:
        return 0


def export_profile_from_files(profile_dir, mods_path):
    """Export a (non-active) profile from its modlist.txt and the mods folder.

    Same item structure as export_modlist. Entries with no folder in
    mods_path are skipped; order is top-to-bottom (reverse of the file).
    """
    with open(os.path.join(profile_dir, "modlist.txt"), encoding="utf-8") as f:
        entries = parse_modlist_txt(f.read())

    items = []
    current_separator = "Unsectioned"
    for mod_name, enabled in reversed(entries):
        mod_path = os.path.join(mods_path, mod_name)
        if not os.path.isdir(mod_path):
            continue
        if mod_name.casefold().endswith("_separator"):
            item = make_separator_item(mod_name, len(items))
            current_separator = item["separatorName"]
            items.append(item)
            continue
        items.append(make_mod_item(
            mod_name, current_separator, _modid_from_meta(mod_path),
            mod_path, enabled, len(items),
        ))
    return items


def list_profiles(organizer):
    """Sorted-or-API-ordered profile names for this MO2 instance."""
    try:
        return list(organizer.profileNames())
    except AttributeError:
        root = os.path.dirname(organizer.profilePath())
        return sorted(
            d for d in os.listdir(root)
            if os.path.isfile(os.path.join(root, d, "modlist.txt"))
        )


def active_profile_name(organizer):
    """Name of the currently active profile."""
    return organizer.profileName()


def profile_dir(organizer, name):
    """Absolute folder of the named profile."""
    try:
        profile = organizer.getProfile(name)
    except AttributeError:
        profile = None
    if profile is not None:
        return profile.absolutePath()
    return os.path.join(os.path.dirname(organizer.profilePath()), name)


def export_profile(organizer, name):
    """Export the named profile; the active one uses the live export."""
    if name.casefold() == active_profile_name(organizer).casefold():
        return export_modlist(organizer)
    return export_profile_from_files(
        profile_dir(organizer, name), organizer.modsPath()
    )
