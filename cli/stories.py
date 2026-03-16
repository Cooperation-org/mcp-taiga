"""User story commands."""

import os
import click
from .client import get_api, get_project, resolve_user, get_status_id, build_tags, parse_earnings, get_tag_labels
from .formatters import table, as_json


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
    if use_json:
        as_json([{'id': m.id, 'username': m.username, 'full_name': m.full_name, 'role_name': m.role_name}
                 for m in proj.members])
    else:
        rows = [(m.id, m.username, m.full_name, m.role_name) for m in proj.members]
        table(['ID', 'Username', 'Name', 'Role'], rows)


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
def create_cmd(project, subject, description, assign, team, cash, tag, status):
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

    story = proj.add_user_story(**kwargs)
    print(f"Created #{story.ref}: {story.subject}")
    if tags:
        print(f"Tags: {', '.join(tags)}")


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
def update_cmd(project, ref, subject, description, assign, team, cash, tag, status):
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
