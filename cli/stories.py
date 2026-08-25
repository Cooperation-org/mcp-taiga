"""User story commands."""

import os
import click
from .client import get_api, get_project, get_memberships, resolve_user, get_status_id, build_tags, parse_earnings, get_tag_labels, parse_due_date, get_all_users, resolve_role, resolve_taiga_user, add_membership, set_membership, admin_role, get_roles
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


@click.command('statuses')
@click.argument('project')
@click.option('--json', 'use_json', is_flag=True, help='JSON output')
def statuses_cmd(project, use_json):
    """List user story statuses defined for a project."""
    api = get_api()
    proj = get_project(api, project)
    import requests
    resp = requests.get(
        f'{api.host}/api/v1/userstory-statuses?project={proj.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    statuses = resp.json()
    if use_json:
        as_json([{'id': s['id'], 'name': s['name']} for s in statuses])
    else:
        rows = [(s['id'], s['name']) for s in statuses]
        table(['ID', 'Name'], rows)


@click.command('add-member')
@click.argument('project')
@click.argument('users', nargs=-1, required=True)
@click.option('--admin/--stakeholder', 'as_admin', default=True,
              help='Add as project admin (default) or as a view-only stakeholder. '
                   'The inviting admin picks; onboard by trust, tighten later.')
@click.option('--role', default=None,
              help="Explicit role name to assign (overrides --admin/--stakeholder role choice)")
@click.option('--dry-run', is_flag=True, help='Show what would be added without changing anything')
@click.option('--json', 'use_json', is_flag=True)
def add_member_cmd(project, users, as_admin, role, dry_run, use_json):
    """Add one or more USERS (username, email, or id) to a PROJECT.

    By default new members are added as project ADMINS with a full-permission
    role, so they can edit and assign tasks immediately. Pass --stakeholder for
    view/comment-only access. The project owner (founder) is always an admin and
    is never affected by this command."""
    api = get_api()
    proj = get_project(api, project)
    if role:
        role_obj = resolve_role(api, proj, role)
    elif as_admin:
        role_obj = admin_role(api, proj) or resolve_role(api, proj, None)
    else:
        role_obj = resolve_role(api, proj, 'Stakeholder')
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
        resp = add_membership(api, proj, role_obj['id'], user['username'], is_admin=as_admin)
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


@click.command('onboard')
@click.argument('project', required=False)
@click.option('--all', 'all_projects', is_flag=True,
              help='Onboard every project you can administer (skips staff-blocked ones)')
@click.option('--role', default=None, help='Full-permission role to grant (default: Product Owner)')
@click.option('--dry-run', is_flag=True, help='Show what would change without writing')
@click.option('--json', 'use_json', is_flag=True)
def onboard_cmd(project, all_projects, role, dry_run, use_json):
    """Make every member of a PROJECT a full admin so they can assign tasks.

    This is the "works for everyone" onboarding primitive: it promotes each
    existing member to is_admin with a full-permission role. It only promotes —
    it never removes anyone and never demotes the founder/owner. Uses PATCH, so
    it is unaffected by the invite-email 500. Idempotent; safe to re-run.

    Pass a PROJECT (slug or id), or --all to sweep every administerable project.
    To ADD new people, use `add-member` (admin by default, --stakeholder to opt
    out)."""
    api = get_api()
    if not project and not all_projects:
        raise SystemExit("Give a PROJECT or use --all.")

    import requests
    all_projs = requests.get(
        f'{api.host}/api/v1/projects?member={_me_id(api)}&page_size=200',
        headers={'Authorization': f'Bearer {api.token}'}).json()
    if all_projects:
        targets = [p for p in all_projs if not p.get('blocked_code')]
        blocked = [p for p in all_projs if p.get('blocked_code')]
        if blocked and not use_json:
            click.echo(f"Skipping {len(blocked)} staff-blocked (read-only) project(s): "
                       + ', '.join(p['slug'] for p in blocked))
    else:
        proj = get_project(api, project)
        pd = next((p for p in all_projs if p['id'] == proj.id), {'id': proj.id, 'slug': proj.slug})
        if pd.get('blocked_code'):
            raise SystemExit(f"Project '{proj.slug}' is staff-blocked (read-only); cannot change members.")
        targets = [pd]

    results = []
    for pd in targets:
        class _P:  # lightweight project handle for helper calls
            id = pd['id']; slug = pd['slug']
        target_role = admin_role(api, _P, prefer=role)
        if not target_role:
            results.append((pd['slug'], '-', 'SKIP: no full-permission role on project'))
            continue
        roles_by_id = {r['id']: r for r in get_roles(api, _P)}
        for m in get_memberships(api, _P):
            if not m.get('user'):
                continue
            name = m.get('full_name') or m.get('user_email') or str(m['user'])
            role_ok = 'modify_us' in roles_by_id.get(m['role'], {}).get('permissions', [])
            if m.get('is_admin') and role_ok:
                continue  # already fully enabled
            fields = {'is_admin': True}
            if not role_ok:
                fields['role'] = target_role['id']
            if dry_run:
                results.append((pd['slug'], name, 'would promote to admin/' + target_role['name']))
                continue
            resp = set_membership(api, m['id'], **fields)
            ok = resp.status_code in (200, 201)
            results.append((pd['slug'], name,
                            'promoted' if ok else f'FAILED {resp.status_code}: {resp.text[:80]}'))

    if use_json:
        as_json([{'project': p, 'member': n, 'result': r} for p, n, r in results])
    else:
        if not results:
            click.echo("Everyone already admin. Nothing to do.")
        else:
            table(['Project', 'Member', 'Result'], results)


def _me_id(api):
    """Return the authenticated user's Taiga id."""
    import requests
    return requests.get(f'{api.host}/api/v1/users/me',
                        headers={'Authorization': f'Bearer {api.token}'}).json()['id']


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
