# Changelog

## Unreleased

- Fail differential runs on frontend internal errors or empty coverage, and confirm unresolved modules after a failed Lean batch.
- Run a fixed-seed differential smoke check in CI and retain revision and differential result metadata.

- Add a reproducible model-revision demonstration (`scripts/revision_demo.py`, `examples/revisions/`): removing the responder's signature rejection makes exactly the six rejection certificates of the two attack scenarios fail; the demo now includes this stage.
- Add randomized differential testing of the Rust exporter against the Python importer with seeded output mutations (`scripts/differential_test.py`).
- Prove injectivity of `Val.key` in Lean (`VAKE.KeyInjective.key_injective`, `key_eq_iff`, `beq_iff_eq`) and add the theorems to the base audit.
- Reuse the compiled Lean library across runs through a content-addressed cache; `VAKE_LEAN_CACHE=0` restores clean-room rebuilds.
- Remove unreachable EDHOC, TLS and KEMTLS semantics (`EDHOC.lean`, setup classes, interpretation branches, deducibility rules) and reject their encoding families in the frontend.
- Describe the per-export binding as a differential check of two independent front ends rather than translation validation.

- Generate concrete Lean execution certificates from model/profile-bound scenario files.
- Add DH and signed-DH examples, including honest agreement and the supplied substitution scenarios.
- Use length-prefixed value keys for symbolic equality and DH/XOR ordering, with normalization regression lemmas.
- Check adversary deducibility with the `admitted_search` tactic.
- Require matching peer fields for named-peer acceptance targets.
- Report `CERTIFICATE_FAILED` and `SCENARIO_ERROR` for failed certificates and invalid scenarios.
- Check message existence in `sent_equal` claims; add `target_state`, `no_accept`, and `signing_key` support.
- Extend the demo, browser workflow, evidence tests, and timing runner to the new examples.

## 0.2.0

- Package the Rust CLI, Lean library, local browser interface, and reproduction scripts under VAKE.
- Add source-archive preflight, component hashes, isolated verification workspaces, and configurable tool paths.
