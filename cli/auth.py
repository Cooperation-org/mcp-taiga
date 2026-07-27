"""Login command — authenticate and store token."""

import getpass
from pathlib import Path
import click
from .client import load_config, login_for_tokens


CONF_PATH = Path.home() / '.mcp-taiga.conf'


@click.command('login')
@click.option('--user', '-u', prompt='Taiga username', help='Your Taiga username')
@click.option('--url', default=None, help='Taiga URL (default: from config)')
@click.option('--save-password/--no-save-password', default=True,
              help='Store the password so the CLI never has to ask again '
                   '(default). --no-save-password keeps token-only auth, which '
                   'stops working once the refresh token expires.')
def login_cmd(user, url, save_password):
    """Authenticate with Taiga and store your credentials.

    The token and refresh token alone are not enough: Taiga expires the refresh
    token after a few days, and a CLI that is used every couple of weeks then
    dies with "token not valid" and needs a human to log in again. Storing the
    username and password in the same 0600 file lets resolve_token mint a new
    session silently, forever, which is the point of a CLI.
    """
    config = load_config()
    taiga_url = url or config['TAIGA_URL']

    password = getpass.getpass(f'Password for {user}@{taiga_url}: ')

    try:
        token, refresh = login_for_tokens(taiga_url, user, password)
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f'Login failed: {e}')

    # Write/update conf file, dropping any prior auth lines we manage.
    managed = ('TAIGA_TOKEN=', 'TAIGA_REFRESH=', 'TAIGA_URL=',
               'TAIGA_USERNAME=', 'TAIGA_PASSWORD=')
    lines = []
    if CONF_PATH.exists():
        for line in CONF_PATH.read_text().splitlines():
            if line.strip().startswith(managed):
                continue
            lines.append(line)

    lines.append(f'TAIGA_URL={taiga_url}')
    lines.append(f'TAIGA_TOKEN={token}')
    if refresh:
        lines.append(f'TAIGA_REFRESH={refresh}')
    if save_password:
        lines.append(f'TAIGA_USERNAME={user}')
        lines.append(f'TAIGA_PASSWORD={password}')
    CONF_PATH.write_text('\n'.join(lines) + '\n')
    CONF_PATH.chmod(0o600)

    if save_password:
        print(f'Logged in as {user}. Credentials saved to {CONF_PATH} (0600). '
              f'This is the last time you have to log in: when the token and '
              f'refresh token expire, the CLI mints a new session itself.')
    elif refresh:
        print(f'Logged in as {user}. Token + refresh token saved to {CONF_PATH}. '
              f'These expire after a few days, and with --no-save-password there '
              f'is nothing to renew them with, so you will have to log in again.')
    else:
        print(f'Logged in as {user}. Token saved to {CONF_PATH} '
              f'(server issued no refresh token). It will expire.')
