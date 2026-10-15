# Scope and limitations

VAKE currently checks a typed JSON model and its formal translation. Interpret each result within the following boundaries.

## Inputs and interpretation

The model schema is `0.1`. The supported profile is schema `1.0` with interpretation `restricted_symbolic_v1`; `fixture_tlv` is a symbolic codec contract, not a binary wire implementation. The frontend rejects unsupported model operations and profiles. Cyclic control-flow graphs are not admitted.

Model acceptance covers syntax, nominal types, references, control flow, and supported backend contracts. It does not establish that the model is an accurate implementation or complete specification of a deployed protocol.

## Export and certificate checks

Export creates Lean source and retains `NOT_CHECKED` as its proof status. Verification independently imports the source and checks concrete source/target and profile bindings together with selected correspondence certificates. This workflow does not prove the Rust exporter correct for every possible input.

The Lean target syntax and evaluator mirror the source constructor for constructor (for example `erase` becomes `clear`), so the source-to-target translation is a renaming and its correspondence theorems are structural. This is not translation validation of a semantics-changing compilation pass. The per-export check is a differential one: two independently written front ends, the Rust exporter and the Python importer, read the same saved JSON, and Lean confirms by `rfl` that their outputs are related by the fixed translation. It catches disagreements between the two front ends; it does not establish that either front end maps the JSON schema to the intended semantics, so importer fidelity remains a trusted assumption. `scripts/differential_test.py` exercises this check on randomized admitted variants of the bundled models and on seeded mutations of the exporter's output; its results cover the generated distribution, not every input.

The Rust frontend, independent Python importer, selected formal semantics and operational profile, Lean kernel, and reported logical axioms form the trust boundary. The audit rejects dependencies outside its allowlist of `propext`, `Classical.choice`, and `Quot.sound`. Read the actual audit to see which axioms each declaration uses.

## Execution examples

Concrete execution certificates are generated from [scenario files](scenarios.md) bound by SHA-256 to a model and profile. The bundled scenarios cover the nonce exchange (honest exchange, malformed-message rejection) and the DH exchange (honest key agreement, man-in-the-middle). They are particular execution results, not universal attacker analysis. The DH man-in-the-middle scenario is a checked counterexample for that unauthenticated model. The signed-DH substitutions are two checked failed attempts, not a proof that every attack fails; honest agreement does not prove authentication. The Announcer terminal certificate and the binding controls apply only to the exact bundled nonce model/profile bytes. Erasing a local value does not erase previously sent bytes or aliases.

Steps that evaluate `literal` terms parse JSON, which Lean does not reduce by `rfl`, so they cannot currently receive concrete certificates. Commutative symbolic operations (DH, XOR) order their arguments by `Val.key`, a length-prefixed structural serialization, and value equality compares these keys. Both are kernel-evaluable, which lets certificates cover DH and signature-verification steps. `Val.key` is proved injective in `Proofs/KeyInjective.lean` (`key_injective`, `key_eq_iff`, `beq_iff_eq`), so key-based value equality coincides with structural equality; the base audit includes these theorems. `Proofs/Normalization.lean` keeps regression lemmas for formerly colliding keys.

The signature example checks symbolic signature construction. Valid and changed-message verification outcomes are separately labeled executable observations; they are not an authentication proof.

## Unsupported security properties

Authentication, secrecy, replay resistance, general attack discovery, secure erasure, computational security, and post-quantum security are not established by the current checks. The model's assessment metadata is descriptive and does not execute a security assessment. A theorem inventory counts declarations, not protocol security properties.

## Execution and distribution

Each run still uses a fresh Lean workspace, but the compiled reusable library is taken from a content-addressed cache (`.vake-cache/`, or `VAKE_CACHE_DIR`). The cache key covers the Lean version, the Lake configuration and every library source file; Lake re-validates module hashes in each workspace. The cache contents are then part of the trusted computing base for that run. Set `VAKE_LEAN_CACHE=0` for a clean-room run that rebuilds the library from source.

The browser service is local and unauthenticated. Keep its host port bound to loopback. It accepts model and profile text up to 2 MiB each and runs one worker at a time. An interrupted or timed-out stage has no successful verification conclusion.

Native builds require the pinned Rust and Lean versions. Platform claims must be backed by execution on that platform. VAKE is licensed under the [Apache License 2.0](../LICENSE).
