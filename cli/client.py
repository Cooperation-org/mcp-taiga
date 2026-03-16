"""Thin wrapper around TaigaAPI for config loading and common lookups."""

import os
import re
from pathlib import Path
from taiga import TaigaAPI


def load_config():
    """Load config from ~/.mcp-taiga.conf or env vars."""
    config = {
        'TAIGA_URL': 'https://taiga.linkedtrust.us',
        'TAIGA_TOKEN': None,
    }

    # Read conf file
    conf_path = Path.home() / '.mcp-taiga.conf'
    if conf_path.exists():
        for line in conf_path.read_text().splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                config[key.strip()] = val.strip()

    # Env vars override
    for key in config:
        env_val = os.environ.get(key)
        if env_val:
            config[key] = env_val

    return config


def get_api():
    """Return authenticated TaigaAPI instance."""
    config = load_config()
    if not config['TAIGA_TOKEN']:
        raise SystemExit(
            "No TAIGA_TOKEN configured.\n"
            "Run: mcp-taiga login"
        )
    api = TaigaAPI(host=config['TAIGA_URL'])
    api.token = config['TAIGA_TOKEN']
    return api


# Cache for project lookups
_project_cache = {}


def get_project(api, slug):
    """Get project by slug, with caching."""
    if slug not in _project_cache:
        projects = api.projects.list()
        for p in projects:
            _project_cache[p.slug] = p
        if slug not in _project_cache:
            # Try partial match
            for p_slug, p in _project_cache.items():
                if slug in p_slug:
                    _project_cache[slug] = p
                    break
    if slug not in _project_cache:
        raise SystemExit(f"Project '{slug}' not found. Run: mcp-taiga projects")
    return _project_cache[slug]


def resolve_user(project, name):
    """Resolve a username/name fragment to a member user ID."""
    name_lower = name.lower()
    for member in project.members:
        if (name_lower == str(member.username).lower() or
                name_lower in str(member.full_name).lower() or
                name_lower == str(member.id)):
            return member.id
    raise SystemExit(
        f"Member '{name}' not found in project. "
        f"Run: mcp-taiga members {project.slug}"
    )


def get_status_id(project, status_name):
    """Resolve a status name to its ID (case-insensitive, partial match)."""
    name_lower = status_name.lower()
    statuses = project.us_statuses
    # Exact match first
    for s in statuses:
        if s.name.lower() == name_lower or s.slug == name_lower:
            return s.id
    # Partial match
    for s in statuses:
        if name_lower in s.name.lower() or name_lower in s.slug:
            return s.id
    available = ', '.join(s.name for s in statuses)
    raise SystemExit(f"Status '{status_name}' not found. Available: {available}")


def build_tags(existing_tags, cook=None, cash=None, extra_tags=None):
    """Build tag list, replacing any existing cook/cash tags."""
    tags = []
    if existing_tags:
        for t in existing_tags:
            # existing_tags from API can be [name, color] pairs or strings
            tag_name = t[0] if isinstance(t, (list, tuple)) else t
            # Strip old cook/cash tags if we're replacing
            if cook is not None and re.match(r'\d+\s*cook', tag_name, re.I):
                continue
            if cash is not None and re.match(r'\d+\s*usd', tag_name, re.I):
                continue
            tags.append(tag_name)

    if cook is not None and cook > 0:
        tags.append(f'{cook}cook')
    if cash is not None and cash > 0:
        tags.append(f'{cash}usd')
    if extra_tags:
        tags.extend(extra_tags)
    return tags


def parse_earnings(tags):
    """Parse cook and cash amounts from a tag list. Returns (cook, cash)."""
    cook = 0
    cash = 0
    if not tags:
        return cook, cash
    for t in tags:
        tag_name = t[0] if isinstance(t, (list, tuple)) else t
        m = re.search(r'(\d+)\s*cook', tag_name, re.I)
        if m:
            cook += int(m.group(1))
        m = re.search(r'(\d+)\s*usd', tag_name, re.I)
        if m:
            cash += int(m.group(1))
    return cook, cash
