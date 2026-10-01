"""Bounded, session-local notification observations. No network or database writes.

First successful snapshot is a baseline. Re-reading it never emits an event.
Unreads are UI state only; clearing them never changes a task lifecycle.
"""
import re

CATEGORIES = ('conversations', 'agents', 'schedules', 'about')
OPEN = frozenset(('running', 'waiting_user', 'waiting_external', 'paused', 'awaiting_review'))


def numeric_version(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'v?(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(?:\+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?', value)
    return tuple(int(part) for part in match.groups()) if match else None


def newer_release(about):
    release = about.get('release') or {}
    local = numeric_version(about.get('installed_version'))
    remote = numeric_version(release.get('release_tag'))
    return bool(release.get('release_status') == 'published' and local and remote and remote > local)


def schedule_identity(item):
    result = (item.get('external_result') or {}).get('observation') or {}
    latest = result.get('latest') or {}
    if latest.get('run_id'):
        return ('result', str(latest['run_id']), str(latest.get('status') or ''))
    last = (item.get('platform_observation') or {}).get('last_run_at')
    return ('platform', str(last)) if last else None


class NotificationState:
    """Only explicit changes, bounded history, and no permanent animation."""
    limit = 2000
    def __init__(self):
        self.initialized = False
        self.seen_runs = {}
        self.announced_runs = {}
        self.agent_states = {}
        self.schedule_states = {}
        self.release_key = None
        self.unread = {category: {} for category in CATEGORIES}
        self.cards = []

    @staticmethod
    def _remember(mapping, key, value=True):
        mapping[key] = value
        while len(mapping) > NotificationState.limit:
            mapping.pop(next(iter(mapping)))

    @staticmethod
    def _prune_history(mapping, visible):
        """Keep the entire current observation plus a bounded retired history.

        Evicting during iteration forgets early members of a large snapshot and
        turns an identical next poll into new events. Prune only after observing
        every current key, and never evict a key present in this snapshot.
        """
        retired = [key for key in mapping if key not in visible]
        for key in retired[:-NotificationState.limit]:
            mapping.pop(key, None)

    def clear(self, category, task_id=None):
        if category not in self.unread:
            return
        if category == 'conversations' and task_id:
            keys = [key for key, value in self.unread[category].items() if value == task_id]
            for key in keys:
                self.unread[category].pop(key, None)
            self.cards = [card for card in self.cards if card['task_id'] != task_id]
        else:
            self.unread[category].clear()
            if category == 'conversations':
                self.cards.clear()

    def counts(self):
        return {category: len(values) for category, values in self.unread.items()}

    def update(self, snapshot):
        runs = {}
        for key in ('runs', 'latest_runs', 'open_runs', 'current_runs'):
            for run in snapshot.get(key) or []:
                if run.get('id'):
                    runs[run['id']] = run
        tasks = {row['id']: row for row in snapshot.get('tasks') or [] if row.get('id')}
        agents = {row['id']: row for row in snapshot.get('agents') or [] if row.get('id')}
        assignments = {}
        for row in snapshot.get('agent_run_assignments') or []:
            if row.get('agent_id') in agents and row.get('run_id') in runs:
                assignments.setdefault(row['run_id'], []).append(agents[row['agent_id']])
        changed = set()
        added = []
        content_changed = False
        baseline = not self.initialized
        for key, run in runs.items():
            if key not in self.seen_runs:
                self.seen_runs[key] = True
                if not baseline:
                    self._remember(self.unread['conversations'], key, run.get('task_id'))
                    changed.add('conversations')
        for key, people in assignments.items():
            run = runs[key]
            task_id = run.get('task_id')
            person = people[0]
            card = {'id': key, 'task_id': task_id, 'title': str((tasks.get(task_id) or {}).get('name') or task_id or '')[:160],
                    'agent': str(person.get('name') or person.get('id') or '')[:80],
                    'avatar': person.get('avatar', 'mint'), 'participants': len(people)}
            if key in self.announced_runs:
                existing = next((item for item in self.cards if item['id'] == key), None)
                if existing is not None and existing != card:
                    existing.update(card)
                    content_changed = True
                continue
            self.announced_runs[key] = True
            if baseline or run.get('status') not in OPEN:
                continue
            self._remember(self.unread['conversations'], key, task_id)
            self.cards.insert(0, card)
            self.cards = self.cards[:50]
            added.append(card)
            changed.add('conversations')
        for key, person in agents.items():
            status = person.get('status') or 'unknown'
            if self.agent_states.get(key) != status:
                if not baseline:
                    self._remember(self.unread['agents'], key)
                    changed.add('agents')
                self.agent_states[key] = status
        for item in snapshot.get('schedules') or []:
            key = item.get('id')
            identity = schedule_identity(item)
            if key and identity and self.schedule_states.get(key) != identity:
                if not baseline:
                    self._remember(self.unread['schedules'], key)
                    changed.add('schedules')
                self.schedule_states[key] = identity
        self._prune_history(self.seen_runs, runs)
        self._prune_history(self.announced_runs, assignments)
        self._prune_history(self.agent_states, agents)
        self._prune_history(self.schedule_states, {item.get('id') for item in snapshot.get('schedules') or [] if schedule_identity(item)})
        about = snapshot.get('about') or {}
        key = (about.get('release') or {}).get('release_tag') if newer_release(about) else None
        if key != self.release_key:
            self.release_key = key
            self.unread['about'].clear()
            if key:
                self.unread['about'][key] = True
                if not baseline:
                    changed.add('about')
        self.initialized = True
        return {'changed': changed, 'cards': added, 'baseline': baseline, 'content_changed': content_changed}


class PauseDeadline:
    """Five seconds of unpaused dwell time; repeated renders do not reset it."""
    def __init__(self, now):
        self.now = now
        self.remaining = 0.0
        self.started = None
        self.paused = False

    def reset(self, seconds=5.0):
        self.remaining = seconds
        self.started = None if self.paused else self.now()

    def pause(self, value):
        if value == self.paused:
            return
        if value and self.started is not None:
            self.remaining = max(0.0, self.remaining - (self.now() - self.started))
            self.started = None
        elif not value:
            self.started = self.now()
        self.paused = value

    def left(self):
        return self.remaining if self.started is None else max(0.0, self.remaining - (self.now() - self.started))
