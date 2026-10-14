from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def read(path: Path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_pairs)

def string(s):

    return '"' + ''.join(('\\"' if c == '"' else '\\\\' if c == '\\' else
                          f'\\u{ord(c):04x}' if ord(c) < 32 or 127 <= ord(c) < 160 else c)
                         for c in s) + '"'

def seq(xs):
    return '[' + ', '.join(xs) + ']'

def pair(*xs):
    return '(' + ', '.join(xs) + ')'

def rec(**fields):
    return '{ ' + ', '.join(f'{k} := {v}' for k, v in fields.items()) + ' }'

def ss(xs):
    return seq(map(string, xs))

def layout(xs):
    return seq(pair(string(x['name']), string(x['type_id'])) for x in xs)

TERM_FIELDS = {
    'ref': ['value_id'], 'literal': ['type_id', 'value'], 'record': ['constructor_id', 'fields'],
    'project': ['record', 'field'], 'encode': ['encoding_id', 'record'],
    'apply': ['primitive_id', 'args'], 'hole': ['hole_id', 'type_id'],
}
STEP_FIELDS = {
    'assign': ['output_value_id', 'term'], 'sample': ['output_value_id', 'generator_id'],
    'invoke': ['primitive_id', 'args', 'result_value_id'], 'receive': ['output_bytes_value_id'],
    'send': ['bytes', 'channel_id'], 'read': ['slot_id', 'output_value_id'], 'write': ['slot_id', 'value'],
    'erase': ['object_id'], 'emit': ['event_name', 'args', 'visibility'],
    'accept': ['target_id', 'key', 'peer'], 'export': ['target_id', 'key'],
    'jump': ['target_block'], 'branch': ['condition', 'true_block', 'false_block'],
    'match': ['result_value_id', 'arms'], 'stop': ['reason'], 'reject': ['target_ids', 'reason'],
}
REGISTRIES = {
    'types': ['id', 'kind', 'parameters', 'fields', 'primitive_ref'],
    'primitives': ['id', 'family', 'mode', 'inputs', 'outcomes', 'failure_profile', 'law_ids'],
    'constructors': ['id', 'type_id', 'fields'], 'encodings': ['id', 'input_type_ids', 'family', 'contract_ids'],
    'values': ['id', 'type_id', 'owner_role', 'storage_kind'],
    'slots': ['id', 'type_id', 'scope', 'lifecycle_policy_id'],
    'messages': ['id', 'constructor_id', 'sender_role', 'receiver_role', 'encoding_id'],
    'targets': ['id', 'role_id', 'stage_id', 'key_type_id', 'peer_mode', 'output_kind',
                'property_definition_ids', 'partnering_profile_id', 'exposure_profile_id'],
    'holes': ['id', 'object_path', 'expected_type_id', 'reason', 'blocked_obligation_ids'],
}

def operational_projection(model):
    def expr(t):
        if t is None:
            return None
        out = {'kind': t['kind'], **{k: t[k] for k in TERM_FIELDS[t['kind']]}}
        if t['kind'] == 'record':
            out['fields'] = [{'name': f['name'], 'term': expr(f['term'])} for f in t['fields']]
        if t['kind'] in ('project', 'encode'):
            out['record'] = expr(t['record'])
        if t['kind'] == 'apply':
            out['args'] = list(map(expr, t['args']))
        return out

    def instruction(s):
        out = {'kind': s['kind'], **{k: s[k] for k in STEP_FIELDS[s['kind']]}}
        for k in ('term', 'bytes', 'value', 'key', 'peer', 'condition'):
            if k in out:
                out[k] = expr(out[k])
        if 'args' in out:
            out['args'] = list(map(expr, out['args']))
        return out

    out = {'protocol': {'id': model['protocol']['id']}}
    for name, fields in REGISTRIES.items():
        out[name] = [{k: v[k] for k in fields} for v in model[name]]
    out['contexts'] = [{**{k: c[k] for k in ('id', 'role_id', 'stage_id', 'purpose')},
                        'recipe': expr(c['recipe'])} for c in model['contexts']]
    out['roles'] = [{**{k: r[k] for k in ('id', 'parameter_value_ids', 'entry_block')},
                     'blocks': [{'id': b['id'], 'steps': list(map(instruction, b['steps'])),
                                 'terminator': instruction(b['terminator'])} for b in r['blocks']]}
                    for r in model['roles']]
    return out

def term(t):
    tag = t['kind']
    s = lambda k: string(t[k])
    if tag == 'ref':
        return f'(.ref {s("value_id")})'
    if tag == 'literal':
        value = json.dumps(t['value'], ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        return f'(.literal {s("type_id")} {string(value)})'
    if tag == 'record':
        fields = '.nil'
        for f in reversed(t['fields']):
            fields = f'(.cons {string(f["name"])} {term(f["term"])} {fields})'
        return f'(.record {s("constructor_id")} {fields})'
    if tag == 'project':
        return f'(.project {term(t["record"])} {s("field")})'
    if tag == 'encode':
        return f'(.encode {s("encoding_id")} {term(t["record"])})'
    if tag == 'apply':
        return f'(.apply {s("primitive_id")} {args(t["args"])})'
    if tag == 'hole':
        return f'(.hole {s("hole_id")} {s("type_id")})'
    raise ValueError(f'unsupported source term {tag}')

def args(xs):
    out = '.nil'
    for t in reversed(xs):
        out = f'(.cons {term(t)} {out})'
    return out

def instruction(s):
    q = lambda k: string(s[k])
    t = lambda k: term(s[k])
    match s['kind']:
        case 'assign': return f'(.assign {q("output_value_id")} {t("term")})'
        case 'sample': return f'(.sample {q("output_value_id")} {q("generator_id")})'
        case 'invoke': return f'(.invoke {q("primitive_id")} {args(s["args"])} {q("result_value_id")})'
        case 'receive': return f'(.receive {q("output_bytes_value_id")})'
        case 'send': return f'(.send {t("bytes")} {q("channel_id")})'
        case 'read': return f'(.read {q("slot_id")} {q("output_value_id")})'
        case 'write': return f'(.write {q("slot_id")} {t("value")})'
        case 'erase': return f'(.erase {q("object_id")})'
        case 'emit': return f'(.emit {q("event_name")} {args(s["args"])} {q("visibility")})'
        case 'accept':
            peer = 'none' if s['peer'] is None else f'(some {t("peer")})'
            return f'(.accept {q("target_id")} {t("key")} {peer})'
        case 'export': return f'(.exportKey {q("target_id")} {t("key")})'
        case _: raise ValueError(f'unsupported source instruction {s["kind"]}')

def ending(t):
    q = lambda k: string(t[k])
    match t['kind']:
        case 'jump': return f'(.jump {q("target_block")})'
        case 'branch': return f'(.branch {term(t["condition"])} {q("true_block")} {q("false_block")})'
        case 'match':
            arms = seq(rec(tag=string(a['tag']), bindings=seq(pair(string(b['payload_name']), string(b['value_id']))
                      for b in a['bindings']), target=string(a['target_block'])) for a in t['arms'])
            return f'(.matchResult {q("result_value_id")} {arms})'
        case 'stop': return f'(.stop {q("reason")})'
        case 'reject': return f'(.reject {ss(t["target_ids"])} {q("reason")})'
        case _: raise ValueError(f'unsupported source terminator {t["kind"]}')

def model_expression(m):
    types = seq(rec(id=string(t['id']), kind=string(t['kind']), parameters=ss(t['parameters']),
                    fields=layout(t['fields']), primitive='none' if t['primitive_ref'] is None else f'(some {string(t["primitive_ref"])})') for t in m['types'])
    primitives = []
    for p in m['primitives']:
        laws = p['law_ids']
        op = {'FreshPerSession': 'fresh', 'HashOperationalFunction': 'hash'}.get(laws[0], laws[0].removeprefix('Op.'))
        if len(laws) != 1:
            raise ValueError('importer requires exactly the reviewed single operational law')
        primitives.append(rec(id=string(p['id']), family=string(p['family']), mode=string(p['mode']), op=string(op),
            failure=string(p['failure_profile']), inputs=seq(pair(string(i['name']), string(i['type_id']), string(i['position_kind'])) for i in p['inputs']),
            outcomes=seq(pair(string(o['tag']), layout(o['payload'])) for o in p['outcomes']), laws=ss(laws)))
    constructors = seq(rec(id=string(c['id']), ty=string(c['type_id']), fields=layout(c['fields'])) for c in m['constructors'])
    encodings = seq(rec(id=string(e['id']), family=string(e['family']), types=ss(e['input_type_ids']), laws=ss(e['contract_ids'])) for e in m['encodings'])
    values = seq(rec(id=string(v['id']), ty=string(v['type_id']), owner=string(v['owner_role']), storage=string(v['storage_kind'])) for v in m['values'])
    slots = seq(rec(id=string(s['id']), ty=string(s['type_id']), scope=string(s['scope']), policy=string(s['lifecycle_policy_id'])) for s in m['slots'])
    targets = seq(rec(id=string(t['id']), role=string(t['role_id']), stage=string(t['stage_id']), ty=string(t['key_type_id']),
                     peerMode=string(t['peer_mode']), outputKind=string(t['output_kind']), properties=ss(t['property_definition_ids']),
                     partnering=string(t['partnering_profile_id']), exposure=string(t['exposure_profile_id'])) for t in m['targets'])
    registry = rec(types=types, primitives=seq(primitives), constructors=constructors, encodings=encodings,
                   values=values, slots=slots, targets=targets)
    roles = []
    for ri, r in enumerate(m['roles']):
        blocks = []
        for bi, b in enumerate(r['blocks']):
            path = f'/roles/{ri}/blocks/{bi}'
            blocks.append(rec(id=string(b['id']), steps=seq(pair(string(f'{path}/steps/{si}'), instruction(s)) for si, s in enumerate(b['steps'])),
                              endLocation=string(path + '/terminator'), ending=ending(b['terminator'])))
        roles.append(rec(id=string(r['id']), parameters=ss(r['parameter_value_ids']), entry=string(r['entry_block']), blocks=seq(blocks)))
    contexts = seq(rec(id=string(c['id']), role=string(c['role_id']), stage=string(c['stage_id']), purpose=string(c['purpose']), recipe=term(c['recipe'])) for c in m['contexts'])
    messages = seq(pair(*(string(x[k]) for k in REGISTRIES['messages'])) for x in m['messages'])
    holes = seq(pair(*(string(x[k]) for k in REGISTRIES['holes'][:-1]), ss(x['blocked_obligation_ids'])) for x in m['holes'])
    return rec(protocol=string(m['protocol']['id']), registry=registry, roles=seq(roles), contexts=contexts, messages=messages, holes=holes)

def environment_expression(p):
    return rec(interpretation=string(p['interpretation']), phase=string(p['phase_policy']),
        exposures=ss(p['exposure_interfaces']), parties=ss(p['parties']),
        credentials=seq(rec(domain=string(c['domain']), reference=string(c['reference']), principal=string(c['principal']), keyOwner=string(c['key_owner'])) for c in p['credentials']),
        kemCorrectness=string(p['kem_correctness']), correctnessErrorSessions=ss(p['correctness_error_sessions']))

def import_export(directory: Path, lean: Path):
    manifest = read(directory / 'export-manifest.json')
    original = directory / 'model.json'
    profile = directory / 'operational-profile.json'
    if sha(original.read_bytes()) != manifest['model_raw_sha256'] or sha(profile.read_bytes()) != manifest['profile_raw_sha256']:
        raise ValueError('source identity mismatch')
    m, p = read(original), read(profile)
    if p['schema_version'] != '1.0' or p['interpretation'] != 'restricted_symbolic_v1':
        raise ValueError('unsupported standalone operational profile')
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or ':' in entry['path']:
            raise ValueError('unsafe export artifact path')
        artifact = directory / relative
        if sha(artifact.read_bytes()) != entry['raw_sha256']:
            raise ValueError(f'artifact fingerprint mismatch: {relative}')
    if operational_projection(m) != read(directory / 'operational-ast.json'):
        raise ValueError('independent full operational AST comparison failed')
    identity = sha(f'{manifest["model_raw_sha256"]}:{manifest["profile_raw_sha256"]}'.encode())
    expected_target = f'VAKE/Generated/M{identity}.lean'
    if [f['path'] for f in manifest['files'] if f['path'].endswith('.lean')] != [expected_target]:
        raise ValueError('unexpected emitted Lean module path')
    imported = f'VAKE.Imported.M{identity}'
    target = f'VAKE.Generated.M{identity}'
    proof = f'VAKE.Generated.B{identity}'
    source_text = f'''import VAKE.Source.Global
set_option maxRecDepth 100000
namespace {imported}
open VAKE
def modelRawSha256 : String := {string(manifest['model_raw_sha256'])}
def profileRawSha256 : String := {string(manifest['profile_raw_sha256'])}
def model : Source.Model :=
{model_expression(m)}
def environment : Environment :=
{environment_expression(p)}
end {imported}
'''
    proof_text = f'''import {imported}
import {target}
import VAKE.Proofs.Global
set_option maxRecDepth 100000
set_option maxHeartbeats 4000000
namespace {proof}
open VAKE
theorem binding : {target}.program = Translate.model {imported}.model := by rfl
theorem profile_binding : {target}.environment = {imported}.environment := by rfl
theorem step_preservation {{s s' : Source.Configuration}} {{a : Source.Action}} {{labels : List Event}}
    (h : Source.Step Symbolic.contract {imported}.model {imported}.environment s a labels s')
    {{t : Target.Configuration}} (related : Translate.Related s t) :
    ∃ t', Target.Step Symbolic.contract {target}.program {target}.environment t (Translate.action a)
      (labels.map Translate.label) t' ∧ Translate.Related s' t' := by
  rw [binding, profile_binding]
  exact Proofs.step_preservation Symbolic.contract _ _ h related
theorem trace_preservation {{s s' : Source.Configuration}} {{as : List Source.Action}} {{labels : List Event}}
    (h : Source.Trace Symbolic.contract {imported}.model {imported}.environment s as labels s') :
    Target.Trace Symbolic.contract {target}.program {target}.environment (Translate.configuration s)
      (as.map Translate.action) labels (Translate.configuration s') := by
  rw [binding, profile_binding]
  exact Proofs.finite_trace_preservation Symbolic.contract _ _ h
theorem trace_reflection (as : List Source.Action) (s : Source.Configuration) (labels : List Event) (t : Target.Configuration)
    (h : Target.Trace Symbolic.contract {target}.program {target}.environment (Translate.configuration s)
      (as.map Translate.action) labels t) :
    ∃ s', Source.Trace Symbolic.contract {imported}.model {imported}.environment s as labels s' ∧ Translate.Related s' t := by
  rw [binding, profile_binding] at h
  exact Proofs.finite_trace_reflection Symbolic.contract _ _ as s labels t h
end {proof}
'''
    for module, content in [(imported, source_text), (proof, proof_text)]:
        path = lean.joinpath(*module.split('.')).with_suffix('.lean')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    for f in manifest['files']:
        if f['path'].endswith('.lean'):
            data = (directory / f['path']).read_bytes()
            if sha(data) != f['raw_sha256']:
                raise ValueError('emitted artifact fingerprint mismatch')
            path = lean / f['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return {'imported': imported, 'target': target, 'proof': proof, 'raw_source_sha256': sha(original.read_bytes()),
            'independent_operational_ast_comparison': 'passed'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export_directory', type=Path)
    parser.add_argument('--lean-dir', type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(import_export(options.export_directory, options.lean_dir), indent=2))
