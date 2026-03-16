# mcp-taiga

CLI for Taiga project management. Wraps the [python-taiga](https://github.com/nephila/python-taiga) library with team/cash tag conventions for tracking earnings on user stories.

## Install

```bash
cd /opt/shared/repos/mcp-taiga
./setup.sh
```

Creates a virtualenv and symlinks `mcp-taiga` into `/opt/shared/tools/`.

## Login

```bash
mcp-taiga login -u myusername
```

Prompts for password, stores token in `~/.mcp-taiga.conf` (per-user, 0600).

## Commands

### Read

```bash
mcp-taiga projects                        # list all projects
mcp-taiga members <project>               # list project members
mcp-taiga list <project>                  # list user stories
mcp-taiga list <project> -s "in progress" # filter by status
mcp-taiga list <project> -a golda         # filter by assignee
mcp-taiga list <project> -t frontend      # filter by tag
mcp-taiga show <project> 42               # show story #42
mcp-taiga earnings <project>              # sum team/cash per user (done stories)
mcp-taiga earnings <project> --all        # sum across all statuses
```

### Write

```bash
mcp-taiga create <project> "Build login page" --team 50 --cash 100 -a golda
mcp-taiga update <project> 42 --team 75 --subject "Updated title"
mcp-taiga move <project> 42 done
mcp-taiga comment <project> 42 "Shipped in v2.1"
mcp-taiga attach <project> 42 ./screenshot.png
mcp-taiga attach <project> 42 https://example.com/spec.pdf
```

All commands support `--json` for machine-readable output where applicable.

## Tag configuration

The `--team` and `--cash` flags map to configurable tag labels:

```
# ~/.mcp-taiga.conf
TAG_TEAM=cook       # --team 50 → "50cook" tag (default)
TAG_CASH=usd        # --cash 100 → "100usd" tag (default)
```

Change these to match your team's conventions (e.g. `TAG_TEAM=points`, `TAG_CASH=dollars`).

## Config file

`~/.mcp-taiga.conf` — one per user:

```
TAIGA_URL=https://taiga.linkedtrust.us
TAIGA_TOKEN=<auto-set by login>
TAG_TEAM=cook
TAG_CASH=usd
```

Environment variables override: `TAIGA_URL`, `TAIGA_TOKEN`, `TAG_TEAM`, `TAG_CASH`.
