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
            separator_name = strip_tags(mod_name).replace("_separator", "").strip()
            current_separator = separator_name
            modlist_data.append({
                "id": None,
                "type": "separator",
                "separatorName": separator_name,
                "modName": separator_name,
                "displayName": mod_name,
                "plugins": [],
                "general": {},
                "installed": {},
                "order": len(modlist_data),
                "tags": extract_tags(mod_name),
                "active": True,
            })
            continue

        mod_path = mod.absolutePath()
        nexus_id = mod.nexusId()
        clean_mod_name = strip_tags(mod_name)
        general_data, installed_files_data = read_meta_ini(mod_path)
        is_active = mod_list.state(mod_name) & mobase.ModState.ACTIVE != 0

        modlist_data.append({
            "id": nexus_id if nexus_id > 0 else clean_mod_name,
            "type": "mod",
            "separatorName": current_separator,
            "modName": clean_mod_name,
            "displayName": mod_name,
            "plugins": get_plugin_files(mod_path),
            "general": general_data,
            "installed": installed_files_data,
            "order": len(modlist_data),
            "tags": extract_tags(mod_name),
            "active": is_active,
        })

    for idx, item in enumerate(modlist_data):
        item["order"] = idx
    return modlist_data
