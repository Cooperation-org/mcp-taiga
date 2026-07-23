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
mcp-taiga add-member <project> alice bob carol            # add users as ADMIN (default)
mcp-taiga add-member <project> dave --stakeholder         # add as view/comment-only instead
mcp-taiga add-member <project> alice --role Back          # pick an explicit role
mcp-taiga add-member <project> alice bob --dry-run        # preview without changes

mcp-taiga onboard <project>                               # make every member of a project an admin
mcp-taiga onboard --all                                   # sweep every administerable project
mcp-taiga onboard <project> --dry-run                     # preview promotions
```

### Onboarding model

The team onboards **by trust**: new members are added as project **admins** by
default so they can edit and assign tasks immediately. The inviting admin can
pass `--stakeholder` to add someone view/comment-only instead. The project
owner (founder) is always an admin and no command demotes them.

`add-member` accepts usernames, emails, or numeric user ids. It is idempotent
(re-running reports existing members as "already a member") and verifies each
add against the live membership list, so a failed invitation-email step on the
Taiga server (which returns HTTP 500 even though the member was created) is
reported correctly as added, not failed.

`onboard` promotes every existing member of a project to a full-permission
admin. It only ever promotes — it never removes anyone and never demotes the
founder. It uses PATCH, so it is unaffected by the invite-email 500, and it is
idempotent. Run it after a new team's project is created, or `--all` to bring a
whole instance up to the "everyone can assign" baseline. Staff-blocked
(read-only) projects are skipped and listed.

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
