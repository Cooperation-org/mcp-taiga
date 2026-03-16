"""Earnings summary — sums cook/cash from done stories per assignee."""

import click
from .client import get_api, get_project, get_status_id, parse_earnings
from .formatters import table, as_json


@click.command('earnings')
@click.argument('project')
@click.option('--status', '-s', default='done', help='Status to sum (default: done)')
@click.option('--all', 'all_statuses', is_flag=True, help='All statuses, not just done')
@click.option('--json', 'use_json', is_flag=True)
def earnings_cmd(project, status, all_statuses, use_json):
    """Sum cook/cash per assignee from completed stories."""
    api = get_api()
    proj = get_project(api, project)

    filters = {'project': proj.id}
    if not all_statuses:
        filters['status'] = get_status_id(proj, status)

    stories = api.user_stories.list(**filters)

    # Build user lookup
    user_cache = {}
    for m in proj.members:
        user_cache[m.id] = m.username

    # Accumulate per user
    totals = {}  # user_id -> {username, cook, cash, stories}
    for s in stories:
        uid = s.assigned_to or 0
        username = user_cache.get(uid, 'unassigned')
        cook, cash = parse_earnings(s.tags)
        if uid not in totals:
            totals[uid] = {'username': username, 'cook': 0, 'cash': 0, 'stories': 0}
        totals[uid]['cook'] += cook
        totals[uid]['cash'] += cash
        totals[uid]['stories'] += 1

    if use_json:
        as_json(list(totals.values()))
    else:
        rows = [(t['username'], t['cook'], f'${t["cash"]}' if t['cash'] else '', t['stories'])
                for t in sorted(totals.values(), key=lambda x: x['cook'], reverse=True)]
        table(['User', 'COOK', 'Cash', 'Stories'], rows)
