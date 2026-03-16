"""Simple output formatters."""

import json


def table(headers, rows):
    """Print a simple aligned table."""
    if not rows:
        print("(no results)")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    # Header
    header_line = '  '.join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print('  '.join('-' * w for w in widths))

    # Rows
    for row in rows:
        print('  '.join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def as_json(data):
    """Print as JSON."""
    print(json.dumps(data, indent=2, default=str))
