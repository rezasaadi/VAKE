# Scope and limitations

VAKE currently checks a typed JSON model and its formal translation. Interpret each result within the following boundaries.

## Inputs and interpretation

The model schema is `0.1`. The supported profile is schema `1.0` with interpretation `restricted_symbolic_v1`; `fixture_tlv` is a symbolic codec contract, not a binary wire implementation. The frontend rejects unsupported model operations and profiles. Cyclic control-flow graphs are not admitted.

Model acceptance covers syntax, nominal types, references, control flow, and supported backend contracts. It does not establish that the model is an accurate implementation or complete specification of a deployed protocol.

## Export and certificate checks

Export creates Lean source and retains `NOT_CHECKED` as its proof status. Verification independently imports the source and checks concrete source/target and profile bindings together with selected correspondence certificates. This workflow does not prove the Rust exporter correct for every possible input.

The Rust frontend, independent Python importer, selected formal semantics and operational profile, Lean kernel, and reported logical axioms form the trust boundary. The audit rejects dependencies outside its allowlist of `propext`, `Classical.choice`, and `Quot.sound`. Read the actual audit to see which axioms each declaration uses.

## Execution examples

The local terminal certificate and global executions apply to the exact bundled nonce model/profile bytes. The global examples cover one honest exchange and one malformed-message rejection. They are particular execution results, not universal attacker analysis. Erasing a local value does not erase previously sent bytes or aliases.

The signature example checks symbolic signature construction. Valid and changed-message verification outcomes are separately labeled executable observations; they are not an authentication proof.

## Unsupported security properties

Authentication, secrecy, replay resistance, general attack discovery, secure erasure, computational security, and post-quantum security are not established by the current checks. The model's assessment metadata is descriptive and does not execute a security assessment. A theorem inventory counts declarations, not protocol security properties.

## Execution and distribution

The browser service is local and unauthenticated. Keep its host port bound to loopback. It accepts model and profile text up to 2 MiB each and runs one worker at a time. An interrupted or timed-out stage has no successful verification conclusion.

Native builds require the pinned Rust and Lean versions. Platform claims must be backed by execution on that platform. See [the consistency report](consistency-report.md) for this revision's validation coverage, and [LICENSE](../LICENSE) for licensing status.
