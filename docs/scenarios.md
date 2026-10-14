# Concrete execution scenarios

A scenario file lists concrete executions of one model and the claims to check about their final states. VAKE turns each scenario into Lean certificates that the kernel checks: one certificate per step, a source trace, the corresponding target trace, and one theorem per claim.

Bundled scenario files live in `examples/scenarios/`:

| File | Model | Scenarios |
|---|---|---|
| `nonce_exchange.scenarios.json` | `nonce_exchange.json` | honest exchange (15 actions), malformed-envelope rejection (6 actions) |
| `dh_exchange.scenarios.json` | `dh_exchange.json` | honest key agreement (32 actions), man-in-the-middle (35 actions) |
| `signed_dh_exchange.scenarios.json` | `signed_dh_exchange.json` | honest key agreement (46 actions), forged share and spliced signature, each rejected without any accepted key (20 actions) |

## Running

`vake demo` and the browser's **Check execution traces** use the bundled file whose hashes match the run's model and profile. For an exported model you can also run:

```bash
python3 scripts/trace_demo.py --export-dir reports/dh-export --out reports/dh-traces \
  --scenarios examples/scenarios/dh_exchange.scenarios.json
```

The result is `trace-result.json` with status `PROVED_UNDER_ASSUMPTIONS` when every certificate is checked, `CERTIFICATE_FAILED` when Lean rejects a step or claim, `SCENARIO_ERROR` when the file is unbound, malformed or not executable, and `INCONCLUSIVE` otherwise (for example a missing tool). The generated Lean file is `lean-check/VAKE/Demo/Global.lean`, and `lean-check/validation/proof-audit.json` lists each declaration with its statement and axiom dependencies.

## Binding to a model

A scenario file records `model_sha256` and `profile_sha256`, the SHA-256 of the exact model and profile bytes. A file bound to other bytes is refused. After editing a model, update the hashes and check that the listed events still describe its execution; Lean rejects any step whose recorded event kind or effect differs.

## File format

```json
{
  "format": "vake-scenarios-0.1",
  "description": "...",
  "model_sha256": "...",
  "profile_sha256": "...",
  "scenarios": [
    { "name": "honest", "description": "...", "actions": [ ... ], "claims": [ ... ] }
  ]
}
```

Scenario and claim names must be identifiers. Unknown fields are rejected.

### Actions

| Action | Meaning | Event |
|---|---|---|
| `{"spawn": {"session": "I1", "role": "Initiator", "party": "Alice"}}` | Start a session (optional `"parameters"`: name → recipe) | `spawn` |
| `{"advance": "I1", "events": ["invoke", "match"]}` | One local step per listed event; each step must record that event kind | as listed |
| `{"deliver": "R1", "recipe": R}` | The adversary delivers bytes to a waiting session | `deliver` |
| `{"remember": "name", "recipe": R}` | The adversary computes and names a value | `attacker_compute` |
| `{"reveal_state": "I1"}`, `{"corrupt": "Alice"}` | Exposures, when the profile enables them | `reveal_state`, `corrupt` |

### Adversary recipes

A recipe `R` is an object with one key: `{"sent": i}` (the i-th sent message), `{"named": n}`, `{"public_key": party}`, `{"signing_key": party}` (setup values, for example spawn parameters), `{"literal": {"type", "json"}}`, `{"atom": {"type", "name", "length"?}}` (a fresh adversary value of a semantic sort), `{"field": {"of": R, "name"}}`, `{"decode": R}`, `{"encode": {"encoding", "record": R}}`, `{"record": {"constructor", "fields": [[name, R], ...]}}`, and `{"call": {"primitive", "args": [R, ...]}}`.

Every value a recipe uses must be deducible from the adversary's knowledge. The `admitted_search` tactic in `lean/VAKE/Proofs/Deduce.lean` constructs these deducibility proofs from roots, literals, adversary atoms, records, encodings, decodings and field projections; the kernel checks the result. If the search fails, the step certificate is not proved and the trace check fails.

### Claims

| Claim | Theorem |
|---|---|
| `{"name": "n", "status": {"session": "R1", "is": "stopped"}}` | The session's final status (`active`, `stopped`, `rejected`) |
| `{"name": "n", "sent_count": 2}` | Number of sent messages |
| `{"name": "n", "no_resume": "R1"}` | The session has no further local step |
| `{"name": "n", "sent_equal": [0, 1]}` | Both indexed messages exist and are equal |
| `{"name": "n", "emitted": [["NonceObserved"]]}` | Names of emitted events, in order |
| `{"name": "n", "accepted": {"session": "I1", "target": "iKey"}}` | The target is accepted |
| `{"name": "n", "target_state": {"session": "R1", "target": "rKey", "is": "rejected"}}` | The target's state (`pending`, `accepted`, `rejected`) |
| `{"name": "n", "no_accept": true}` | No session recorded an accept event |
| `{"name": "n", "same_key": [["I1", "iKey"], ["R1", "rKey"]]}` | Both accepted keys exist and are equal |
| `{"name": "n", "different_key": [["I1", "iKey"], ["R1", "rKey"]]}` | Both accepted keys exist and differ |
| `{"name": "n", "adversary_holds_key": {"name": "k", "session": "R1", "target": "rKey"}}` | The adversary's named value equals the accepted key |

## Scope

Read each claim from its theorem statement in `proof-audit.json`. These certificates concern particular executions. A man-in-the-middle scenario exhibits one execution in which acceptance happens with keys the adversary computes; it is a checked counterexample for this model, not a general attack search. Likewise, the signed DH substitutions show two attempts that fail; they do not show that every attack fails. Agreement in an honest scenario does not prove authentication or secrecy for all executions.

Evaluating a `literal` term parses JSON, which Lean does not reduce by `rfl`. Steps that evaluate literals therefore cannot currently receive concrete certificates; the bundled models avoid them.
