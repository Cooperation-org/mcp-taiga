"""User story commands."""

import os
import click
from .client import get_api, get_project, get_memberships, resolve_user, get_status_id, build_tags, parse_earnings, get_tag_labels, parse_due_date, get_all_users, resolve_role, resolve_taiga_user, add_membership
from .formatters import table, as_json


@click.command('users')
@click.option('--json', 'use_json', is_flag=True)
def users_cmd(use_json):
    """List all Taiga users."""
    api = get_api()
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
        if 'x-pagination-next' not in resp.headers or not resp.headers['x-pagination-next']:
            break
        page += 1

    if use_json:
        as_json([{'id': u['id'], 'username': u.get('username', ''), 'full_name': u.get('full_name', '')}
                 for u in users])
    else:
        rows = [(u['id'], u.get('username', ''), u.get('full_name', '')) for u in users]
        table(['ID', 'Username', 'Name'], rows)


@click.command('projects')
@click.option('--json', 'use_json', is_flag=True, help='JSON output')
def projects_cmd(use_json):
    """List all projects."""
    api = get_api()
    projects = api.projects.list()
    if use_json:
        as_json([{'id': p.id, 'slug': p.slug, 'name': p.name} for p in projects])
    else:
        rows = [(p.id, p.slug, p.name) for p in projects]
        table(['ID', 'Slug', 'Name'], rows)


@click.command('members')
@click.argument('project')
@click.option('--json', 'use_json', is_flag=True)
def members_cmd(project, use_json):
    """List project members."""
    api = get_api()
    proj = get_project(api, project)
    memberships = get_memberships(api, proj)
    if use_json:
        as_json([{'id': m.get('user'), 'username': m.get('username', ''),
                  'full_name': m.get('full_name', ''), 'role_name': m.get('role_name', '')}
                 for m in memberships])
    else:
        rows = [(m.get('user', ''), m.get('username', ''), m.get('full_name', ''), m.get('role_name', ''))
                for m in memberships]
        table(['ID', 'Username', 'Name', 'Role'], rows)


@click.command('add-member')
@click.argument('project')
@click.argument('users', nargs=-1, required=True)
@click.option('--role', default=None,
              help="Role to assign (default: Stakeholder, or first project role)")
@click.option('--dry-run', is_flag=True, help='Show what would be added without changing anything')
@click.option('--json', 'use_json', is_flag=True)
def add_member_cmd(project, users, role, dry_run, use_json):
    """Add one or more USERS (username, email, or id) to a PROJECT."""
    api = get_api()
    proj = get_project(api, project)
    role_obj = resolve_role(api, proj, role)
    all_users = get_all_users(api)
    # Memberships report `user` (id) reliably; `username` is often null. Dedup
    # and verify by id.
    existing_ids = {m.get('user') for m in get_memberships(api, proj)}

    # Resolve every identifier up front so a typo fails before any writes.
    resolved = [(ident, resolve_taiga_user(api, ident, all_users)) for ident in users]

    # Attempt each add, capturing any error text. We do NOT trust the HTTP
    # status alone: Taiga creates the membership and THEN tries to email an
    # invitation, so a failed mail backend returns 500 even though the member
    # was added. Final truth comes from re-reading the membership list below.
    attempted = {}  # user id -> error text (or None on a clean status)
    results = []
    for ident, user in resolved:
        uname = user.get('username') or user.get('full_name') or str(user['id'])
        if user['id'] in existing_ids:
            results.append((ident, uname, 'already a member'))
            continue
        if dry_run:
            results.append((ident, uname, f'would add as {role_obj["name"]}'))
            continue
        resp = add_membership(api, proj, role_obj['id'], user['username'])
        attempted[user['id']] = None if resp.status_code in (200, 201) else f'{resp.status_code}: {resp.text[:120]}'

    if attempted:
        now_ids = {m.get('user') for m in get_memberships(api, proj)}
        for ident, user in resolved:
            if user['id'] not in attempted:
                continue
            uname = user.get('username') or user.get('full_name') or str(user['id'])
            if user['id'] in now_ids:
                results.append((ident, uname, f'added as {role_obj["name"]}'))
            else:
                results.append((ident, uname, f'FAILED ({attempted[user["id"]]})'))

    if use_json:
        as_json([{'input': i, 'username': u, 'result': r} for i, u, r in results])
    else:
        table(['Input', 'Username', 'Result'], results)


def _tag_names(tags):
    """Extract tag name strings from Taiga's tag format."""
    if not tags:
        return []
    return [t[0] if isinstance(t, (list, tuple)) else t for t in tags]


def _assignee_name(api, story):
    """Get assignee username from story."""
    if not story.assigned_to:
        return ''
    try:
        user = api.users.get(story.assigned_to)
        return user.username
    except Exception:
        return str(story.assigned_to)


@click.command('list')
@click.argument('project')
@click.option('--status', '-s', help='Filter by status name')
@click.option('--assign', '-a', help='Filter by assignee')
@click.option('--tag', '-t', help='Filter by tag')
@click.option('--json', 'use_json', is_flag=True)
def list_cmd(project, status, assign, tag, use_json):
    """List user stories in a project."""
    api = get_api()
    proj = get_project(api, project)

    # Build API filters
    filters = {'project': proj.id}
    if status:
        filters['status'] = get_status_id(proj, status)

    stories = api.user_stories.list(**filters)

    # Client-side filters
    if assign:
        assign_id = resolve_user(proj, assign)
        stories = [s for s in stories if s.assigned_to == assign_id]
    if tag:
        tag_lower = tag.lower()
        stories = [s for s in stories if any(tag_lower in tn.lower() for tn in _tag_names(s.tags))]

    if use_json:
        as_json([{
            'ref': s.ref, 'subject': s.subject, 'status': s.status_extra_info.get('name', ''),
            'assigned_to': s.assigned_to, 'tags': _tag_names(s.tags),
        } for s in stories])
    else:
        rows = []
        for s in stories:
            status_name = s.status_extra_info.get('name', '') if hasattr(s, 'status_extra_info') else ''
            tags_str = ', '.join(_tag_names(s.tags))
            team_label, cash_label = get_tag_labels()
            team_val, cash_val = parse_earnings(s.tags)
            value = []
            if team_val:
                value.append(f'{team_val}{team_label}')
            if cash_val:
                value.append(f'${cash_val}')
            rows.append((s.ref, s.subject[:60], status_name, value and ' '.join(value) or '', tags_str))
        table(['#', 'Subject', 'Status', 'Value', 'Tags'], rows)


@click.command('show')
@click.argument('project')
@click.argument('ref', type=int)
def show_cmd(project, ref):
    """Show a user story by reference number."""
    api = get_api()
    proj = get_project(api, project)
    story = proj.get_userstory_by_ref(ref)

    assignee = _assignee_name(api, story) if story.assigned_to else 'unassigned'
    status_name = story.status_extra_info.get('name', '') if hasattr(story, 'status_extra_info') else ''
    team_label, cash_label = get_tag_labels()
    team_val, cash_val = parse_earnings(story.tags)

    print(f"#{story.ref}  {story.subject}")
    print(f"Status: {status_name}  |  Assigned: {assignee}")
    if getattr(story, 'due_date', None):
        print(f"Due: {story.due_date}")
    if team_val or cash_val:
        parts = []
        if team_val:
            parts.append(f'{team_val} {team_label.upper()}')
        if cash_val:
            parts.append(f'${cash_val} {cash_label.upper()}')
        print(f"Value: {' + '.join(parts)}")
    if story.tags:
        print(f"Tags: {', '.join(_tag_names(story.tags))}")
    if story.description:
        print(f"\n{story.description}")

    # Show comments
    try:
        # python-taiga doesn't have a direct comments list, use history
        pass  # TODO: fetch comments via API if needed
    except Exception:
        pass


@click.command('create')
@click.argument('project')
@click.argument('subject')
@click.option('--description', '-d', default='', help='Description text')
@click.option('--assign', '-a', help='Assign to username')
@click.option('--team', type=int, help='Team token amount (adds tag)')
@click.option('--cash', type=int, help='Cash amount (adds tag)')
@click.option('--tag', '-t', multiple=True, help='Additional tags')
@click.option('--status', '-s', help='Status name')
@click.option('--due', help='Due date (YYYY-MM-DD)')
def create_cmd(project, subject, description, assign, team, cash, tag, status, due):
    """Create a user story."""
    api = get_api()
    proj = get_project(api, project)

    kwargs = {
        'subject': subject,
        'description': description,
    }

    tags = build_tags([], team=team, cash=cash, extra_tags=list(tag))
    if tags:
        kwargs['tags'] = tags

    if assign:
        kwargs['assigned_to'] = resolve_user(proj, assign)

    if status:
        kwargs['status'] = get_status_id(proj, status)

    if due:
        kwargs['due_date'] = parse_due_date(due)

    story = proj.add_user_story(**kwargs)
    print(f"Created #{story.ref}: {story.subject}")
    if tags:
        print(f"Tags: {', '.join(tags)}")
    if due:
        print(f"Due: {kwargs['due_date']}")


@click.command('update')
@click.argument('project')
@click.argument('ref', type=int)
@click.option('--subject', help='New subject')
@click.option('--description', '-d', help='New description')
@click.option('--assign', '-a', help='Assign to username')
@click.option('--team', type=int, help='Set team token amount')
@click.option('--cash', type=int, help='Set cash amount')
@click.option('--tag', '-t', multiple=True, help='Add tags')
@click.option('--status', '-s', help='Set status')
@click.option('--due', help='Set due date (YYYY-MM-DD)')
def update_cmd(project, ref, subject, description, assign, team, cash, tag, status, due):
    """Update a user story."""
    api = get_api()
    proj = get_project(api, project)
    story = proj.get_userstory_by_ref(ref)

    if subject:
        story.subject = subject
    if description is not None:
        story.description = description
    if assign:
        story.assigned_to = resolve_user(proj, assign)
    if status:
        story.status = get_status_id(proj, status)
    if due:
        story.due_date = parse_due_date(due)

    if team is not None or cash is not None or tag:
        story.tags = build_tags(story.tags, team=team, cash=cash, extra_tags=list(tag))

    story.update()
    print(f"Updated #{story.ref}: {story.subject}")


@click.command('move')
@click.argument('project')
@click.argument('ref', type=int)
@click.argument('status')
def move_cmd(project, ref, status):
    """Move a story to a new status."""
    api = get_api()
    proj = get_project(api, project)
    story = proj.get_userstory_by_ref(ref)
    story.status = get_status_id(proj, status)
    story.update()
    print(f"#{story.ref} → {status}")


@click.command('comment')
@click.argument('project')
@click.argument('ref', type=int)
@click.argument('text')
def comment_cmd(project, ref, text):
    """Add a comment to a story."""
    api = get_api()
    proj = get_project(api, project)
    story = proj.get_userstory_by_ref(ref)
    story.add_comment(text)
    print(f"Comment added to #{story.ref}")


@click.command('attach')
@click.argument('project')
@click.argument('ref', type=int)
@click.argument('path_or_url')
@click.option('--description', '-d', default='', help='Attachment description')
def attach_cmd(project, ref, path_or_url, description):
    """Attach a file or URL to a story."""
    api = get_api()
    proj = get_project(api, project)
    story = proj.get_userstory_by_ref(ref)

    if path_or_url.startswith('http://') or path_or_url.startswith('https://'):
        # URLs go as comments since Taiga attachments are file-only
        link_text = f"[{description or path_or_url}]({path_or_url})"
        story.add_comment(link_text)
        print(f"Link added to #{story.ref}: {path_or_url}")
    else:
        if not os.path.exists(path_or_url):
            raise SystemExit(f"File not found: {path_or_url}")
        story.attach(path_or_url, description=description)
        print(f"File attached to #{story.ref}: {path_or_url}")
