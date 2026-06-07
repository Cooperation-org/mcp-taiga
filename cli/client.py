"""Thin wrapper around TaigaAPI for config loading and common lookups."""

import os
import re
from pathlib import Path
from taiga import TaigaAPI
from taiga.requestmaker import RequestMaker


def load_config():
    """Load config from ~/.mcp-taiga.conf or env vars."""
    config = {
        'TAIGA_URL': 'https://taiga.linkedtrust.us',
        'TAIGA_TOKEN': None,
        'TAG_TEAM': 'cook',
        'TAG_CASH': 'usd',
        'DEFAULT_PROJECT': None,
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


def get_default_project():
    """Return default project slug from config, or error."""
    config = load_config()
    proj = config.get('DEFAULT_PROJECT')
    if not proj:
        raise SystemExit(
            "No project specified and no DEFAULT_PROJECT configured.\n"
            "Set DEFAULT_PROJECT in ~/.mcp-taiga.conf or pass project as argument."
        )
    return proj


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
    api.token_type = 'Bearer'
    api.raw_request = RequestMaker(
        '/api/v1', config['TAIGA_URL'], config['TAIGA_TOKEN'], 'Bearer',
        api.tls_verify, proxies=api.proxies,
    )
    api._init_resources()
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


def get_memberships(api, project):
    """Fetch project memberships via REST API (works with Taiga 6+)."""
    import requests
    resp = requests.get(
        f'{api.host}/api/v1/memberships?project={project.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    return resp.json()


def resolve_user(project, name, api=None):
    """Resolve a username/name fragment to a member user ID."""
    if api is None:
        api = get_api()
    name_lower = name.lower()
    memberships = get_memberships(api, project)
    for m in memberships:
        uid = m.get('user')
        uname = (m.get('username') or '').lower()
        fname = (m.get('full_name') or '').lower()
        email = (m.get('email') or '').lower()
        if (name_lower == uname or
                name_lower in fname or
                name_lower == email or
                name_lower == str(uid)):
            return uid
    names = [m.get('full_name') or m.get('email') or str(m.get('user')) for m in memberships]
    raise SystemExit(
        f"Member '{name}' not found in project. "
        f"Members: {', '.join(names)}"
    )


def get_status_id(project, status_name):
    """Resolve a user story status name to its ID (case-insensitive, partial match)."""
    import requests
    api = get_api()
    resp = requests.get(
        f'{api.host}/api/v1/userstory-statuses?project={project.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    statuses = resp.json()
    name_lower = status_name.lower()
    # Exact match first
    for s in statuses:
        if s['name'].lower() == name_lower or s.get('slug', '').lower() == name_lower:
            return s['id']
    # Partial match
    for s in statuses:
        if name_lower in s['name'].lower():
            return s['id']
    available = ', '.join(s['name'] for s in statuses)
    raise SystemExit(f"Status '{status_name}' not found. Available: {available}")


def get_tag_labels():
    """Return (team_label, cash_label) from config."""
    config = load_config()
    return config['TAG_TEAM'], config['TAG_CASH']


def parse_due_date(value):
    """Validate a due date string and return it in Taiga's YYYY-MM-DD format.

    Accepts an ISO date (YYYY-MM-DD). Raises SystemExit with a clear message
    on a malformed date so the CLI fails loudly instead of silently dropping it.
    """
    from datetime import datetime
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        raise SystemExit(
            f"Invalid due date '{value}'. Use YYYY-MM-DD (e.g. 2026-06-14)."
        )


def build_tags(existing_tags, team=None, cash=None, extra_tags=None):
    """Build tag list, replacing any existing team/cash tags."""
    team_label, cash_label = get_tag_labels()
    team_re = re.compile(rf'\d+\s*{re.escape(team_label)}', re.I)
    cash_re = re.compile(rf'\d+\s*{re.escape(cash_label)}', re.I)

    tags = []
    if existing_tags:
        for t in existing_tags:
            tag_name = t[0] if isinstance(t, (list, tuple)) else t
            if team is not None and team_re.match(tag_name):
                continue
            if cash is not None and cash_re.match(tag_name):
                continue
            tags.append(tag_name)

    if team is not None and team > 0:
        tags.append(f'{team}{team_label}')
    if cash is not None and cash > 0:
        tags.append(f'{cash}{cash_label}')
    if extra_tags:
        tags.extend(extra_tags)
    return tags


def parse_earnings(tags):
    """Parse team and cash amounts from a tag list. Returns (team, cash)."""
    team_label, cash_label = get_tag_labels()
    team_re = re.compile(rf'(\d+)\s*{re.escape(team_label)}', re.I)
    cash_re = re.compile(rf'(\d+)\s*{re.escape(cash_label)}', re.I)

    team_total = 0
    cash_total = 0
    if not tags:
        return team_total, cash_total
    for t in tags:
        tag_name = t[0] if isinstance(t, (list, tuple)) else t
        m = team_re.search(tag_name)
        if m:
            team_total += int(m.group(1))
        m = cash_re.search(tag_name)
        if m:
            cash_total += int(m.group(1))
    return team_total, cash_total
