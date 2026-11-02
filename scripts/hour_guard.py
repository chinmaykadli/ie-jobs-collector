"""Avoid a second collector pass after this UTC hour's data was published."""
import datetime as dt
import json
import os
from pathlib import Path


def already_published(health, now):
    try:
        checked = dt.datetime.fromisoformat(health['checked_at'].replace('Z', '+00:00'))
        if checked.tzinfo is None:
            return False
        checked = checked.astimezone(dt.timezone.utc)
        now = now.astimezone(dt.timezone.utc)
        return checked.replace(minute=0, second=0, microsecond=0) == now.replace(minute=0, second=0, microsecond=0)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


if __name__ == '__main__':
    try:
        health = json.loads(Path('docs-data/health.json').read_text())
    except (OSError, ValueError):
        health = {}
    skip = already_published(health, dt.datetime.now(dt.timezone.utc))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'skip={str(skip).lower()}\n')
    print('Collector skipped: this UTC hour already has published data.' if skip else 'No published data for this UTC hour; collecting.')
