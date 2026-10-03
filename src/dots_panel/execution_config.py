"""Explicit dispatch requests and immutable observed configuration evidence.

Recording a request is not runtime verification or dispatch. Old rows stay unknown.
"""
import json
import math
import re
import time

FIELDS = ('requested_model', 'requested_effort', 'actual_model', 'actual_effort',
          'config_verification', 'config_provider', 'config_observed_at', 'config_evidence')
EFFORTS = frozenset(('none','minimal','low','medium','high','xhigh','max','ultra','persistent'))
DEFAULT_MODEL, DEFAULT_EFFORT = 'gpt-6.1-sol', 'high'


def normalize_config(**values):
    unknown = set(values) - set(FIELDS)
    if unknown:
        raise ValueError('Unknown configuration fields')
    result = {key: values.get(key) for key in FIELDS}
    result['config_verification'] = result['config_verification'] or 'unknown'
    if result['config_verification'] not in ('unknown','requested','verified'):
        raise ValueError('Invalid configuration verification')
    for key in ('requested_model','actual_model'):
        value = result[key]
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}',value)):
            raise ValueError('Invalid model identifier')
    for key in ('requested_effort','actual_effort'):
        if result[key] is not None and result[key] not in EFFORTS:
            raise ValueError('Invalid reasoning effort')
    requested = result['requested_model'] is not None or result['requested_effort'] is not None
    actual = result['actual_model'] is not None or result['actual_effort'] is not None
    if requested and not (result['requested_model'] and result['requested_effort']):
        raise ValueError('A configuration request needs both model and effort')
    if actual and not (result['actual_model'] and result['actual_effort']):
        raise ValueError('An actual configuration observation needs both model and effort')
    if actual and result['config_verification'] != 'verified':
        raise ValueError('Actual configuration requires verified provider observation')
    if result['config_verification'] == 'requested' and not requested:
        raise ValueError('Requested verification needs explicit request fields')
    if result['config_verification'] == 'verified' and not actual:
        raise ValueError('Verified configuration requires actual fields')
    if result['config_verification'] == 'unknown' and (requested or actual):
        raise ValueError('Unknown verification cannot claim configuration values')
    for key, limit in (('config_provider',200),('config_evidence',2000)):
        value = result[key]
        if value is not None:
            if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):
                raise ValueError('Invalid configuration provenance')
            result[key]=value.strip()
    observed = result['config_observed_at']
    if observed is not None:
        from .app import timestamp
        observed=timestamp(observed)
        if not math.isfinite(observed) or observed<0 or observed>time.time()+300:
            raise ValueError('Invalid configuration observation time')
        result['config_observed_at']=observed
    if result['config_verification'] != 'unknown' and not all(result.get(k) is not None for k in ('config_provider','config_observed_at','config_evidence')):
        raise ValueError('Configuration evidence needs provider, observation time and evidence')
    return result


def config_from_row(row):
    data=dict(row or {})
    return {k: data.get(k, 'unknown' if k=='config_verification' else None) for k in FIELDS}


def migrate(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(assignment_episodes)')}
    for key in FIELDS:
        if key not in columns:
            definition="TEXT NOT NULL DEFAULT 'unknown'" if key=='config_verification' else 'REAL' if key=='config_observed_at' else 'TEXT'
            db.execute('ALTER TABLE assignment_episodes ADD COLUMN '+key+' '+definition)
    db.execute('CREATE TRIGGER IF NOT EXISTS immutable_assignment_config BEFORE UPDATE OF '+','.join(FIELDS)+" ON assignment_episodes BEGIN SELECT RAISE(ABORT,'Assignment configuration is immutable'); END;")
    columns={r[1] for r in db.execute('PRAGMA table_info(event_attributions)')}
    if 'execution_config_json' not in columns:
        db.execute("ALTER TABLE event_attributions ADD COLUMN execution_config_json TEXT")


def dispatch_plan():
    return {'record_only': True, 'dispatches': False, 'model': DEFAULT_MODEL,
            'reasoning_effort': DEFAULT_EFFORT, 'ceiling': {'model':'gpt-6-astra','reasoning_effort':'ultra'},
            'actual_model': None, 'actual_effort': None, 'config_verification':'unknown'}


def config_label(config, language='zh'):
    data=config_from_row(config)
    en=language=='en'
    if data['config_verification']=='verified':
        return ('Observed ' if en else '已观测 ')+data['actual_model']+' / '+data['actual_effort']
    if data['config_verification']=='requested':
        return ('Requested ' if en else '请求 ')+data['requested_model']+' / '+data['requested_effort']+(' · actual unknown' if en else ' · 实际未知')
    return 'Model unknown' if en else '模型未知'
