"""Taiga Task commands (subtasks of user stories)."""

import click
from .client import get_api, get_project, get_default_project, resolve_user, get_tag_labels, build_tags, parse_earnings
from .formatters import table, as_json


def _resolve_project(api, project_slug):
    """Resolve project from arg or default config."""
    if not project_slug:
        project_slug = get_default_project()
    return get_project(api, project_slug)


def _task_assignee_name(api, task):
    """Get assignee username from task."""
    if not task.assigned_to:
        return ''
    try:
        user = api.users.get(task.assigned_to)
        return user.username
    except Exception:
        return str(task.assigned_to)


def _task_status_name(task):
    """Get status name from task."""
    if hasattr(task, 'status_extra_info') and task.status_extra_info:
        return task.status_extra_info.get('name', '')
    return ''


def _get_task_status_id(api, project, status_name):
    """Resolve a task status name to its ID."""
    import requests
    resp = requests.get(
        f'{api.host}/api/v1/task-statuses?project={project.id}',
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
    raise SystemExit(f"Task status '{status_name}' not found. Available: {available}")


@click.group('task')
def task_group():
    """Manage Taiga tasks (subtasks of user stories)."""
    pass


@task_group.command('list')
@click.argument('project', required=False)
@click.option('--story', '-u', type=int, help='Filter by user story ref')
@click.option('--assign', '-a', help='Filter by assignee')
@click.option('--status', '-s', help='Filter by status')
@click.option('--json', 'use_json', is_flag=True)
def task_list(project, story, assign, status, use_json):
    """List tasks in a project."""
    api = get_api()
    proj = _resolve_project(api, project)

    filters = {'project': proj.id}

    if story:
        # Resolve story ref to ID
        us = proj.get_userstory_by_ref(story)
        filters['user_story'] = us.id

    if status:
        filters['status'] = _get_task_status_id(api, proj, status)

    tasks = api.tasks.list(**filters)

    if assign:
        assign_id = resolve_user(proj, assign)
        tasks = [t for t in tasks if t.assigned_to == assign_id]

    if use_json:
        as_json([{
            'ref': t.ref, 'subject': t.subject,
            'status': _task_status_name(t),
            'assigned_to': t.assigned_to,
            'user_story': getattr(t, 'user_story', None),
        } for t in tasks])
    else:
        rows = []
        for t in tasks:
            assignee = _task_assignee_name(api, t) or 'unassigned'
            rows.append((t.ref, t.subject[:60], _task_status_name(t), assignee))
        table(['#', 'Subject', 'Status', 'Assigned'], rows)


@task_group.command('show')
@click.argument('ref', type=int)
@click.argument('project', required=False)
def task_show(ref, project):
    """Show a task by reference number."""
    api = get_api()
    proj = _resolve_project(api, project)

    import requests
    resp = requests.get(
        f'{api.host}/api/v1/tasks/by_ref?ref={ref}&project={proj.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    data = resp.json()

    assignee = ''
    if data.get('assigned_to'):
        try:
            user = api.users.get(data['assigned_to'])
            assignee = user.username
        except Exception:
            assignee = str(data['assigned_to'])

    status_name = ''
    if data.get('status_extra_info'):
        status_name = data['status_extra_info'].get('name', '')

    us_ref = ''
    if data.get('user_story_extra_info'):
        us_ref = f"#{data['user_story_extra_info'].get('ref', '')}"

    print(f"Task #{data['ref']}  {data['subject']}")
    print(f"Status: {status_name}  |  Assigned: {assignee or 'unassigned'}  |  Story: {us_ref}")
    if data.get('description'):
        print(f"\n{data['description']}")


@task_group.command('assign')
@click.argument('ref', type=int)
@click.argument('username')
@click.argument('project', required=False)
def task_assign(ref, username, project):
    """Assign a task to a user by name."""
    api = get_api()
    proj = _resolve_project(api, project)

    import requests
    # Get task by ref
    resp = requests.get(
        f'{api.host}/api/v1/tasks/by_ref?ref={ref}&project={proj.id}',
        headers={'Authorization': f'Bearer {api.token}'},
    )
    resp.raise_for_status()
    data = resp.json()

    user_id = resolve_user(proj, username)

    # Update task
    resp = requests.patch(
        f'{api.host}/api/v1/tasks/{data["id"]}',
        headers={'Authorization': f'Bearer {api.token}', 'Content-Type': 'application/json'},
        json={'assigned_to': user_id, 'version': data['version']},
    )
    resp.raise_for_status()
    print(f"Task #{ref} assigned to {username}")


@task_group.command('create')
@click.argument('subject')
@click.argument('project', required=False)
@click.option('--story', '-u', type=int, help='User story ref to attach to')
@click.option('--assign', '-a', help='Assign to username')
@click.option('--status', '-s', help='Status name')
@click.option('--description', '-d', default='', help='Description')
@click.option('--team', type=int, help='Team token amount (adds tag)')
@click.option('--cash', type=int, help='Cash amount (adds tag)')
@click.option('--tag', '-t', multiple=True, help='Additional tags')
def task_create(subject, project, story, assign, status, description, team, cash, tag):
    """Create a task."""
    api = get_api()
    proj = _resolve_project(api, project)

    import requests
    payload = {
        'project': proj.id,
        'subject': subject,
        'description': description,
    }

    tags = build_tags([], team=team, cash=cash, extra_tags=list(tag))
    if tags:
        payload['tags'] = tags

    if story:
        us = proj.get_userstory_by_ref(story)
        payload['user_story'] = us.id

    if assign:
        payload['assigned_to'] = resolve_user(proj, assign)

    if status:
        payload['status'] = _get_task_status_id(api, proj, status)

    resp = requests.post(
        f'{api.host}/api/v1/tasks',
        headers={'Authorization': f'Bearer {api.token}', 'Content-Type': 'application/json'},
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"Created task #{data['ref']}: {data['subject']}")
    if tags:
        print(f"Tags: {', '.join(tags)}")
