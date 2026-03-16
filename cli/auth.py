"""Login command — authenticate and store token."""

import getpass
from pathlib import Path
import click
from taiga import TaigaAPI
from .client import load_config


CONF_PATH = Path.home() / '.mcp-taiga.conf'


@click.command('login')
@click.option('--user', '-u', prompt='Taiga username', help='Your Taiga username')
@click.option('--url', default=None, help='Taiga URL (default: from config)')
def login_cmd(user, url):
    """Authenticate with Taiga and store your token."""
    config = load_config()
    taiga_url = url or config['TAIGA_URL']

    password = getpass.getpass(f'Password for {user}@{taiga_url}: ')

    api = TaigaAPI(host=taiga_url)
    try:
        api.auth(user, password)
    except Exception as e:
        raise SystemExit(f'Login failed: {e}')

    # Write/update conf file
    lines = []
    if CONF_PATH.exists():
        for line in CONF_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith('TAIGA_TOKEN=') or stripped.startswith('TAIGA_URL='):
                continue
            lines.append(line)

    lines.append(f'TAIGA_URL={taiga_url}')
    lines.append(f'TAIGA_TOKEN={api.token}')
    CONF_PATH.write_text('\n'.join(lines) + '\n')
    CONF_PATH.chmod(0o600)

    print(f'Logged in as {user}. Token saved to {CONF_PATH}')
