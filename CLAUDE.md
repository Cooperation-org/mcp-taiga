# mcp-taiga

CLI tool wrapping Taiga REST API via python-taiga. Used by the LinkedTrust/What's Cookin' team for task management with cook/cash tag conventions.

## Setup

```bash
cd /opt/shared/repos/mcp-taiga
./setup.sh          # creates .venv, installs deps, shows config instructions
mcp-taiga login     # authenticate with username/password, stores token in ~/.mcp-taiga.conf
```

Symlinked into `/opt/shared/tools/mcp-taiga` so it's in PATH for all users.

## Architecture

- `cli/client.py` — TaigaAPI wrapper, config loading from `~/.mcp-taiga.conf`, project/user/status resolution
- `cli/stories.py` — all user story CRUD commands (list, show, create, update, move, comment, attach)
- `cli/earnings.py` — cook/cash earnings summation per assignee
- `cli/auth.py` — login command (username/password → token)
- `cli/formatters.py` — table and JSON output
- `cli/main.py` — click group wiring
- `mcp-taiga` — bash wrapper that resolves symlink and runs via venv python
- `mcp/` — placeholder for optional MCP shim (not yet implemented)

## Config

Per-user config in `~/.mcp-taiga.conf`:
```
TAIGA_URL=https://taiga.linkedtrust.us
TAIGA_TOKEN=<bearer-token>
```
Env vars `TAIGA_URL` and `TAIGA_TOKEN` override the conf file.

## Tag conventions

- `Ncook` — cook tokens earned (e.g. `50cook`)
- `Nusd` — cash payment in USD (e.g. `100usd`)
- Tags are on user stories, parsed by `earnings` command
