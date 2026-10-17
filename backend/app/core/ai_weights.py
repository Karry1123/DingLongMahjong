"""Production EV weights: startup-only V1 preference with a frozen V0 fallback.

Independent of offline tools, AST policy snapshots, simulators and optimizers.
Only the twelve validated named weights can change; other V0 values stay fixed.
"""
import hashlib
import json
import logging
import math
from contextlib import contextmanager
from pathlib import Path
from . import ev_engine, tenpai_model, call_decision

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'
BOUNDS = json.loads((CONFIG_DIR/'ai_core_bounds.json').read_text(encoding='utf-8'))
MODULES = {'ev_engine':ev_engine,'tenpai_model':tenpai_model}
logger = logging.getLogger(__name__)

def read_policy(config_dir=CONFIG_DIR):
    directory=Path(config_dir)
    baseline=json.loads((directory/'ai_weights_v0.json').read_text(encoding='utf-8'))
    optimized=directory/'ai_weights_optimized.json'
    source=optimized if optimized.exists() else directory/'ai_weights_v0.json'
    cfg=json.loads(source.read_text(encoding='utf-8'))
    if cfg.get('schema_version')!=baseline['schema_version'] or cfg.get('source_hashes')!=baseline['source_hashes']:
        raise ValueError('AI policy schema or V0 provenance mismatch')
    weights=cfg.get('weights',{})
    if set(weights)!=set(baseline['weights']):raise ValueError('Missing or unexpected AI weights')
    for key,value in weights.items():
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError(f'Invalid AI weight: {key}')
        if key in BOUNDS:
            bound=BOUNDS[key]
            if not bound['min']<=value<=bound['max'] or (bound['integer'] and value!=int(value)):
                raise ValueError(f'AI weight outside hard bounds: {key}')
        elif value!=baseline['weights'][key]:raise ValueError(f'Noncore AI weight must stay at V0: {key}')
    if not weights['ev_engine._YAKUHAI_SINGLE_POTENTIAL']<=weights['ev_engine._YAKUHAI_PAIR_POTENTIAL']<=weights['ev_engine._YAKUHAI_PUNG_POTENTIAL']:
        raise ValueError('Inconsistent yakuhai potential ordering')
    return cfg,source

def initialize_ai_weights(config_dir=CONFIG_DIR):
    cfg,source=read_policy(config_dir) # Fully validate before changing any module.
    for key in BOUNDS:
        module,attribute=key.split('.',1)
        value=cfg['weights'][key]
        setattr(MODULES[module],attribute,int(value) if BOUNDS[key]['integer'] else value)
    # call_decision imported a scalar by value; keep PASS and discard EV aligned.
    call_decision.SHANTEN_PENALTY=ev_engine.SHANTEN_PENALTY
    status={'version':'V1' if source.name=='ai_weights_optimized.json' else 'V0',
        'path':str(source),'fingerprint':hashlib.sha256(json.dumps(cfg['weights'],sort_keys=True).encode()).hexdigest()}
    logger.info('AI EV policy loaded: %s (%s)',status['version'],status['fingerprint'])
    return status

@contextmanager
def ai_weights_session(config_dir=CONFIG_DIR):
    """Keep weights active during app lifespan; restore when the app stops.

    This also keeps in-process test apps from leaking startup state into rule tests.
    """
    previous={key:getattr(MODULES[key.split('.')[0]],key.split('.')[1]) for key in BOUNDS}
    previous_call=call_decision.SHANTEN_PENALTY
    try:
        yield initialize_ai_weights(config_dir)
    finally:
        for key,value in previous.items():
            module,attribute=key.split('.',1);setattr(MODULES[module],attribute,value)
        call_decision.SHANTEN_PENALTY=previous_call
