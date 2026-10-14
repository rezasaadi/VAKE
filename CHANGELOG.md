# Changelog

## Unreleased

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
