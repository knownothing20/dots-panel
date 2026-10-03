"""Bounded, session-local notification observations. No network or database writes.

First successful snapshot is a baseline. Re-reading it never emits an event.
Unreads are UI state only; clearing them never changes a task lifecycle.
"""
import re
import json
import os
import stat
import tempfile
from pathlib import Path

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


class NotificationStorage:
    """Private local viewer state. Errors are explicit; never writes the ledger."""
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().absolute()
        self.path = self.directory / 'config' / 'notifications.json'
        self.error = None
        self.persistence = 'persistent'
        self.invalid_saved_state = False

    def _validate(self):
        for path in (self.directory, *self.directory.parents, self.path.parent, self.path):
            if path.is_symlink():
                raise ValueError('Notification storage cannot use symlinks')
        if not self.directory.is_dir():
            raise ValueError('Notification DATA directory does not exist')
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        for path in (self.directory, self.path.parent):
            if not path.is_dir() or path.stat().st_mode & 0o077:
                raise ValueError('Notification storage requires private directories')
        if self.path.exists() and (not stat.S_ISREG(self.path.stat().st_mode) or self.path.stat().st_mode & 0o077):
            raise ValueError('Notification storage requires a private regular file')

    def _failed(self, exc):
        self.persistence = 'session_only'
        self.error = 'Notification storage unavailable; session-only unread state: ' + str(exc)

    def load(self):
        try:
            self._validate()
            if not self.path.exists():
                return None
            if self.path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('Notification state exceeds supported size')
            try:
                value = json.loads(self.path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError):
                self.invalid_saved_state = True
                raise
            if not isinstance(value, dict) or value.get('version') != 1:
                self.invalid_saved_state = True
                raise ValueError('Invalid notification state')
            return value
        except (OSError, ValueError, UnicodeError) as exc:
            # A failed initial read cannot safely overwrite unread state we never loaded.
            self.invalid_saved_state = True
            self._failed(exc)
            return None

    def save(self, state):
        if self.invalid_saved_state:
            return False
        temporary = None
        try:
            self._validate()
            content = json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
            if len(content) > 16 * 1024 * 1024:
                raise ValueError('Notification state exceeds supported size')
            fd, temporary = tempfile.mkstemp(prefix='.notifications-', dir=self.path.parent)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            self._validate()
            os.replace(temporary, self.path)
            temporary = None
            self.persistence, self.error = 'persistent', None
            return True
        except (OSError, ValueError, UnicodeError, TypeError) as exc:
            self._failed(exc)
            return False
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


class NotificationState:
    """Only explicit changes, bounded history, and no permanent animation."""
    limit = 2000
    def __init__(self, storage=None):
        self.storage = storage
        self.initialized = False
        self.seen_runs = {}
        self.announced_runs = {}
        self.agent_states = {}
        self.schedule_states = {}
        self.release_key = None
        self.unread = {category: {} for category in CATEGORIES}
        self.cards = []
        self.requirement_stream_id = None
        self.requirement_states = {}
        self.requirement_counters = {}
        self.requirement_event_signatures = {}
        if storage is not None:
            saved = storage.load()
            if saved:
                try:
                    for field in ('seen_runs', 'announced_runs', 'agent_states', 'schedule_states', 'requirement_states', 'requirement_counters', 'requirement_event_signatures'):
                        value = saved.get(field, {})
                        if not isinstance(value, dict):
                            raise ValueError('Invalid notification state map')
                        setattr(self, field, value)
                    self.schedule_states = {k: tuple(v) for k,v in self.schedule_states.items()}
                    self.unread = {category: dict(saved.get('unread', {}).get(category, {})) for category in CATEGORIES}
                    self.cards = self._normalize_cards(saved.get('cards', []))
                    self.initialized = bool(saved.get('initialized'))
                    self.release_key = saved.get('release_key')
                    self.requirement_stream_id = saved.get('requirement_stream_id')
                except (ValueError, TypeError, AttributeError) as exc:
                    storage.invalid_saved_state = True
                    storage._failed(exc)
                    self.__init__()
                    self.storage = storage

    @property
    def persistence(self):
        return self.storage.persistence if self.storage is not None else 'session_only'

    @property
    def storage_error(self):
        return self.storage.error if self.storage is not None else None

    def _save(self):
        if self.storage is not None:
            self.storage.save({'version': 1, **{field: getattr(self, field) for field in ('initialized', 'seen_runs', 'announced_runs', 'agent_states', 'schedule_states', 'release_key', 'unread', 'cards', 'requirement_stream_id', 'requirement_states', 'requirement_counters', 'requirement_event_signatures')}})

    def _requirements(self, snapshot):
        stream = snapshot.get('requirement_stream_id')
        if stream is None:
            return False, [], False
        events = snapshot.get('requirement_events') or []
        signatures = {str(e['id']): json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events if e.get('id') is not None}
        counters = snapshot.get('requirement_counters') or {kind: max((int(e['id']) for e in events if e.get('kind') == kind), default=0) for kind in ('receipt', 'state', 'owner', 'link')}
        reset = stream != self.requirement_stream_id or any(counters.get(k, 0) < v for k, v in self.requirement_counters.items()) or any(signatures.get(k) != v for k, v in self.requirement_event_signatures.items())
        baseline = reset or not self.initialized
        if reset:
            self.requirement_states = {}
            self.cards = [c for c in self.cards if c.get('kind') != 'requirement']
            self.unread['conversations'] = {k: v for k, v in self.unread['conversations'].items() if not k.startswith('requirement:')}
        added = []
        changed = False
        for req in snapshot.get('requirements') or []:
            key = 'requirement:' + req['id']
            identity = [req.get('source_event_id'), req.get('current_event_id', 0), req.get('current_owner_event_id', 0)]
            owner = req.get('owner') or {}
            card = {'id': key, 'kind': 'requirement', 'requirement_id': req['id'], 'task_id': req['task_id'], 'title': req.get('summary', '')[:160], 'status': req.get('status', 'received'), 'agent': owner.get('name') or 'Unknown', 'avatar': 'mint', 'participants': 1, 'owner': owner, 'agent_record': {k: owner[k] for k in ('name', 'name_en', 'portrait') if owner.get(k)}}
            previous = self.requirement_states.get(key)
            existing = next((c for c in self.cards if c['id'] == key), None)
            if existing is not None and existing != card:
                existing.update(card); changed = True
            if not baseline and identity != previous:
                self.unread['conversations'][key] = req['task_id']
                self.cards = [c for c in self.cards if c['id'] != key]
                self.cards.insert(0, card); self.cards = self._normalize_cards(self.cards)
                added.append(card)
            self.requirement_states[key] = identity
        self.requirement_stream_id = stream
        self.requirement_counters = counters
        self.requirement_event_signatures = signatures
        return baseline, added, changed

    @staticmethod
    def _normalize_cards(cards):
        if not isinstance(cards, list) or any(not isinstance(card, dict) or not isinstance(card.get('id'), str) for card in cards):
            raise ValueError('Invalid saved notification cards')
        result, legacy = [], 0
        for card in cards:
            if card.get('kind') == 'requirement' or card['id'].startswith('requirement:'):
                result.append(card)
            elif legacy < 50:
                result.append(card)
                legacy += 1
        return result

    @staticmethod
    def _remember(mapping, key, value=True):
        mapping[key] = value
        # Unread requirements are obligations, not an evictable observation cache.
        retired = [key for key in mapping if not str(key).startswith('requirement:')]
        for key in retired[:-NotificationState.limit]:
            mapping.pop(key, None)

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

    def clear(self, category, task_id=None, requirement_id=None):
        if category not in self.unread:
            return
        if category == 'conversations':
            if requirement_id is not None:
                keys = ['requirement:' + requirement_id]
            else:
                # Merely opening a task or activity list is not viewing a requirement.
                keys = [key for key, value in self.unread[category].items() if not key.startswith('requirement:') and (task_id is None or value == task_id)]
            for key in keys:
                self.unread[category].pop(key, None)
            self.cards = [card for card in self.cards if card['id'] not in keys]
        else:
            self.unread[category].clear()
        self._save()

    def counts(self):
        return {category: len(values) for category, values in self.unread.items()}

    def update(self, snapshot):
        requirement_baseline, requirement_added, requirement_changed = self._requirements(snapshot)
        linked_runs = {rid for req in snapshot.get('requirements') or [] for rid in req.get('run_ids') or []}
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
        added = list(requirement_added)
        content_changed = requirement_changed
        baseline = not self.initialized or requirement_baseline
        if requirement_added:
            changed.add('conversations')
        for key, run in runs.items():
            if key not in self.seen_runs:
                self.seen_runs[key] = True
                if not baseline and key not in linked_runs:
                    self._remember(self.unread['conversations'], key, run.get('task_id'))
                    changed.add('conversations')
        for key, people in assignments.items():
            run = runs[key]
            task_id = run.get('task_id')
            person = people[0]
            card = {'id': key, 'task_id': task_id, 'title': str((tasks.get(task_id) or {}).get('name') or task_id or '')[:160],
                    'agent': str(person.get('name') or person.get('id') or '')[:80],
                    'avatar': person.get('avatar', 'mint'), 'participants': len(people),
                    'agent_record': {field: person[field] for field in ('id', 'name', 'name_en', 'avatar', 'portrait', 'portrait_spec') if field in person}}
            if key in self.announced_runs:
                existing = next((item for item in self.cards if item['id'] == key), None)
                if existing is not None and existing != card:
                    existing.update(card)
                    content_changed = True
                continue
            self.announced_runs[key] = True
            if baseline or key in linked_runs or run.get('status') not in OPEN:
                continue
            self._remember(self.unread['conversations'], key, task_id)
            self.cards.insert(0, card)
            self.cards = self._normalize_cards(self.cards)
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
        self._save()
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
