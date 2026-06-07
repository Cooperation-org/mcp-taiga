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
        'TAIGA_USERNAME': None,
        'TAIGA_PASSWORD': None,
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


def _jwt_expired(token, skew=60):
    """True if a JWT access token is expired (or expires within `skew` seconds).

    Non-JWT or undecodable tokens are treated as NOT expired (best-effort use).
    """
    import base64
    import json
    import time
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return False
    exp = claims.get('exp')
    if not exp:
        return False
    return time.time() >= (exp - skew)


def login_for_token(host, username, password):
    """Authenticate username/password against Taiga and return an access token."""
    import requests
    resp = requests.post(
        f'{host}/api/v1/auth',
        json={'type': 'normal', 'username': username, 'password': password},
        timeout=15,
    )
    if not resp.ok:
        raise SystemExit(
            f"Taiga login failed for '{username}' ({resp.status_code}). "
            f"Check TAIGA_USERNAME/TAIGA_PASSWORD."
        )
    return resp.json()['auth_token']


def _cache_token(token):
    """Persist a freshly-minted token back to ~/.mcp-taiga.conf when that file
    exists, so subsequent invocations reuse it until it expires. Env-only
    credential setups (no conf file) simply re-login each run."""
    conf_path = Path.home() / '.mcp-taiga.conf'
    if not conf_path.exists():
        return
    try:
        lines = conf_path.read_text().splitlines()
        out, found = [], False
        for line in lines:
            if line.strip().startswith('TAIGA_TOKEN='):
                out.append(f'TAIGA_TOKEN={token}')
                found = True
            else:
                out.append(line)
        if not found:
            out.append(f'TAIGA_TOKEN={token}')
        conf_path.write_text('\n'.join(out) + '\n')
    except Exception:
        pass  # caching is best-effort; never block a working token


def resolve_token(config):
    """Return a usable Taiga token, refreshing via username/password when the
    stored token is missing or expired. Keeps token-only setups working."""
    token = config.get('TAIGA_TOKEN')
    username = config.get('TAIGA_USERNAME')
    password = config.get('TAIGA_PASSWORD')

    if token and not _jwt_expired(token):
        return token

    if username and password:
        fresh = login_for_token(config['TAIGA_URL'], username, password)
        _cache_token(fresh)
        return fresh

    if token:
        return token  # expired but no creds to refresh; let the API try anyway

    raise SystemExit(
        "No Taiga credentials configured.\n"
        "Run: mcp-taiga login, or set TAIGA_USERNAME and TAIGA_PASSWORD."
    )


def get_api():
    """Return authenticated TaigaAPI instance."""
    config = load_config()
    token = resolve_token(config)
    config['TAIGA_TOKEN'] = token
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


def get_all_users(api):
    """Fetch every Taiga user (paginated)."""
    import requests
    users = []
    page = 1
    while True:
        resp = requests.get(
            f'{api.host}/api/v1/users?page={page}',
            headers={'Authorization': f'Bearer {api.token}'},
        )
        if not resp.ok:
            break
        batch = resp.json()
        if not batch:
            break
        users.extend(batch)
        if not resp.headers.get('x-pagination-next'):
            break
        page += 1
    return users


def get_roles(api, project):
    """Fetch the roles defined on a project."""
    import requests
    resp = requests.get(
        f'{api.host}/api/v1/roles?project={project.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    return resp.json()


def resolve_role(api, project, role_name):
    """Resolve a role name (case-insensitive, partial) to a role dict.

    With no name, default to 'Stakeholder' if the project has it, else the
    first role. Returns the full role dict so callers can show the name used.
    """
    roles = get_roles(api, project)
    if not roles:
        raise SystemExit(f"Project '{project.slug}' has no roles defined.")
    if role_name:
        nl = role_name.lower()
        for r in roles:
            if r['name'].lower() == nl:
                return r
        for r in roles:
            if nl in r['name'].lower():
                return r
        avail = ', '.join(r['name'] for r in roles)
        raise SystemExit(f"Role '{role_name}' not found. Available: {avail}")
    for r in roles:
        if r['name'].lower() == 'stakeholder':
            return r
    return roles[0]


def resolve_taiga_user(api, ident, users=None):
    """Resolve an identifier (username, email, full name, or numeric id) to a
    full Taiga user dict. Raises SystemExit with candidates when the match is
    ambiguous or absent."""
    if users is None:
        users = get_all_users(api)
    il = str(ident).strip().lower()
    # Exact username / email / id first
    for u in users:
        if (il == (u.get('username') or '').lower()
                or il == (u.get('email') or '').lower()
                or il == str(u.get('id'))):
            return u
    # Fall back to full-name / substring match
    matches = [
        u for u in users
        if il in (u.get('full_name') or '').lower()
        or il in (u.get('username') or '').lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"No Taiga user matches '{ident}'.")
    listed = ', '.join(f"{u['username']} ({u.get('full_name') or '?'})" for u in matches[:10])
    raise SystemExit(
        f"'{ident}' is ambiguous. Candidates: {listed}. "
        f"Use an exact username."
    )


def add_membership(api, project, role_id, username):
    """Create a project membership. Returns the requests.Response so the caller
    can distinguish created (201), already-a-member, and other errors."""
    import requests
    return requests.post(
        f'{api.host}/api/v1/memberships',
        headers={
            'Authorization': f'Bearer {api.token}',
            'Content-Type': 'application/json',
        },
        json={'project': project.id, 'role': role_id, 'username': username},
    )


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
