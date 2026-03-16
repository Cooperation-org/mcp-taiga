"""mcp-taiga CLI — manage Taiga tasks with cook/cash tags."""

import click
from .stories import (
    projects_cmd, members_cmd, list_cmd, show_cmd,
    create_cmd, update_cmd, move_cmd, comment_cmd, attach_cmd,
)
from .earnings import earnings_cmd


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """Manage Taiga tasks with cook/cash tags."""
    pass


cli.add_command(projects_cmd)
cli.add_command(members_cmd)
cli.add_command(list_cmd)
cli.add_command(show_cmd)
cli.add_command(create_cmd)
cli.add_command(update_cmd)
cli.add_command(move_cmd)
cli.add_command(comment_cmd)
cli.add_command(attach_cmd)
cli.add_command(earnings_cmd)


if __name__ == '__main__':
    cli()
