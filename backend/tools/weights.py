"""Strict offline weight schema and isolated, frozen V0 policy modules."""
import ast
import hashlib
import importlib
import json
import math
import sys
import types
from functools import lru_cache
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT / "weights_schema.json").read_text(encoding="utf-8"))
PARAMETERS = SCHEMA["parameters"]
POOL = ROOT / "policy_pool"

def load_weights(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_weights(cfg)

def validate_weights(cfg):
    if cfg.get("schema_version") != 1 or cfg.get("source_hashes") != SCHEMA["source_hashes"]:
        raise ValueError("Wrong schema or V0 source fingerprint")
    values = cfg.get("weights", {})
    if set(values) != set(PARAMETERS):
        raise ValueError("Missing or unknown parameters")
    for key, spec in PARAMETERS.items():
        value = values[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not spec["min"] <= value <= spec["max"]:
            raise ValueError(f"Out-of-bounds parameter: {key}")
        if spec["integer"] and value != int(value):
            raise ValueError(f"Expected integer: {key}")
    if values['call_decision._JUNK_CUT_SPEED_BONUS_MIN'] > values['call_decision._JUNK_CUT_SPEED_BONUS_MAX']:
        raise ValueError("Call bonus minimum exceeds maximum")
    for ordered in (
        ('ev_engine._YAKUHAI_SINGLE_POTENTIAL','ev_engine._YAKUHAI_PAIR_POTENTIAL','ev_engine._YAKUHAI_PUNG_POTENTIAL'),
        ('ev_engine._SHAPE_PENCHAN','ev_engine._SHAPE_KANCHAN','ev_engine._SHAPE_RYANMEN'),
        ('danger_model.BASE_HONOR_DEAD','danger_model.BASE_HONOR_LIVE'),
    ):
        if [values[k] for k in ordered] != sorted(values[k] for k in ordered):
            raise ValueError('Inconsistent physical ordering: ' + str(ordered))
    if values['tenpai_model._P_FLOOR'] + values['tenpai_model._P_SPAN'] > .95:
        raise ValueError('Closed-hand tenpai prior exceeds probability ceiling')
    if cfg.get('policy_version') == 'V2-claims':
        from app.core.claim_v2 import validate_claim_weights
        validate_claim_weights(cfg.get('claim_weights', {}))
        v1 = json.loads((POOL/'baseline_v1.json').read_text(encoding='utf-8'))
        if values != v1['weights']:
            raise ValueError('V2 must freeze all 165 V1 base weights')
    elif cfg.get('policy_version') == 'V4-R1':
        from tools.sensitivity_scan import validate_r1
        validate_r1(cfg)
    elif cfg.get('policy_version') == 'V4-guard':
        from tools.v4_experiment import validate_v4
        validate_v4(cfg)
    elif cfg.get('policy_version') == 'V3-guard':
        from tools.v3_experiment import validate_v3
        validate_v3(cfg)
    elif 'claim_weights' in cfg or cfg.get('policy_version'):
        raise ValueError('Unknown policy version')
    return cfg

def fingerprint(cfg):
    identity = cfg['weights']
    if cfg.get('policy_version') in ('V3-guard', 'V4-guard', 'V4-R1'):
        identity = [cfg['policy_version'], identity, cfg['runtime_hashes']]
    elif cfg.get('policy_version'):
        identity = [cfg['policy_version'], identity, cfg['claim_weights']]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

@lru_cache(maxsize=8)
def _runtime(serialized, accelerated=True):
    cfg = validate_weights(json.loads(serialized))
    if cfg.get('policy_version') == 'V4-R1':
        from tools.sensitivity_scan import guard_runtime
        return guard_runtime(cfg, accelerated)
    if cfg.get('policy_version') == 'V4-guard':
        from tools.v4_experiment import guard_runtime
        return guard_runtime(cfg, accelerated)
    if cfg.get('policy_version') == 'V3-guard':
        from tools.v3_experiment import guard_runtime
        return guard_runtime(cfg, accelerated)
    name = "app.core._offline_" + fingerprint(cfg)[:16]
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT.parent / 'app' / 'core')]
    package.__package__ = name
    sys.modules[name] = package
    modules = {}
    for dependency in ("constants", "evaluator", "mapper", "pool_tracker", "scoring", "action_generator"):
        sys.modules[name + "." + dependency] = importlib.import_module("app.core." + dependency)
    for module in ('danger_model', 'tenpai_model', 'ev_engine', 'call_decision'):
        path = ROOT / 'policy_sources' / (module + '.py')
        source = path.read_text(encoding='utf-8')
        if hashlib.sha256(source.encode()).hexdigest() != SCHEMA['source_hashes'][module]:
            raise ValueError("Frozen policy source was modified")
        tree = ast.parse(source)
        class Replace(ast.NodeTransformer):
            def visit_Constant(self, node):
                key = SCHEMA['locations'].get(f'{module}:{node.lineno}:{node.col_offset}')
                if key:
                    value = cfg['weights'][key]
                    if PARAMETERS[key]['integer']: value = int(value)
                    return ast.copy_location(ast.Constant(value), node)
                return node
        tree = ast.fix_missing_locations(Replace().visit(tree))
        obj = types.ModuleType(name + '.' + module)
        obj.__package__ = name
        obj.__file__ = str(path)
        sys.modules[obj.__name__] = obj
        exec(compile(tree, str(path), 'exec'), obj.__dict__)
        modules[module] = obj
    # Only lazy imports in frozen EV are rule-only action generators.
    # Rebind their package for those imports; retain parameterized static references.
    for obj in modules.values(): obj.__dict__['__package__'] = 'app.core'
    from tools.ev_acceleration import install
    if accelerated: install(modules)
    for key in list(sys.modules):
        if key == name or key.startswith(name + '.'):
            del sys.modules[key]
    if cfg.get('policy_version') == 'V2-claims':
        from app.core.claim_v2 import install as install_claims
        install_claims(modules, cfg['claim_weights'])
    # LRU now bounds complete policy graphs instead of leaking per-trial packages.
    return modules

def runtime(cfg, accelerated=True):
    return _runtime(json.dumps(cfg, sort_keys=True), accelerated)
