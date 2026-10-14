# VAKE browser reference

For a first run, use the [guided walkthrough](start-here.md). This guide explains the evidence behind each stage.

After a native build, run `python3 -m ui.server --port 8765`; alternatively, follow the [Docker guide](docker.md). Saved runs remain available after a server restart.

## Inputs and run identity

Select a bundled example, upload UTF-8 JSON, or expand **Paste JSON or choose a profile**. A blank profile selects the bundled `restricted_symbolic_v1` profile. Model and profile text are limited to 2 MiB each.

Each run saves its own immutable model/profile pair. **Run and input details** shows its identifier and SHA-256 values; **View saved JSON** shows the input. The role overview describes the model and does not describe a completed execution.

## Check the model

**Check model** runs the Rust parser, type checker, and supported-contract checks. **Command result and raw output** retains the CLI JSON, exit code, UTC timestamps, stdout, and stderr.

`CHECKED` means frontend acceptance. `PARSE_ERROR` and `TYPE_ERROR` retain the diagnostic. The bundled type-mismatch model is expected to fail with exit code `1`; a completed job can therefore represent an expected rejection. `OPEN_OBLIGATION` with exit code `2` permits export but blocks closed-model verification.

## Export and run Lean

**Create Lean files** translates the model with the saved profile. **Inspect generated files** gives access to generated source, original inputs, the export manifest, and the source map. Export alone retains `NOT_CHECKED` as its proof status.

**Run Lean checks** independently imports the source, checks source/target and profile bindings, compiles the certificates, and audits logical axioms. **Checked under assumptions** corresponds to `PROVED_UNDER_ASSUMPTIONS`. Read **Lean audit details** and **Certificate scope and assumptions** for the exact checked declarations and assumptions.

Lean modules use the `VAKE` namespace. Input-bound modules are stored under `VAKE/Generated/` and `VAKE/Imported/` inside the isolated Lean workspace.

The exact nonce input/profile pair enables its Announcer terminal certificate. The signature example checks signature construction and records separate executable observations. General models use the correspondence route. These routes do not establish authentication, secrecy, or replay resistance.

## Executions and altered-binding controls

**Check execution traces** is available when a bundled scenario file is bound to the run's exact model and profile: the nonce exchange (honest execution and malformed-message rejection), DH (honest agreement and man-in-the-middle), and signed DH (honest agreement and two rejected substitutions). See [scenarios](scenarios.md). **Inspect checked steps** shows network actions, local actions, events, values, source JSON pointers, and declaration names. **Trace certificates and audit** provides the Lean certificate and statement/axiom inventory.

Inspect the run's trace evidence for its action counts, events, sends, and final-state claims.

**Additional check: altered bindings** runs two mutations. Success requires rejection at the intended target or profile binding; an arbitrary process failure does not count as a successful control.

**Proof inventory and trust assumptions** combines the completed audits and removes duplicate declaration names. Counts depend on the selected certificate route and stages completed. Inspect the recorded inventories instead of assuming a fixed count. They are declaration inventories, not counts of cryptographic security proofs.

## Evidence and replay

**Download evidence ZIP** saves an idle run's current state, including unfinished checks. The service refuses downloads while a stage is queued or running. **Logs and saved files** provides history, stage results, hashes, file filtering, raw views, and individual downloads. **Reproduce this run from the command line** shows recorded commands and tool versions.

Shared bundle copies normalize machine paths in metadata and logs. Semantic inputs and Lean files keep their exact bytes. The bundle manifest records original and bundled hashes. If an unchanged semantic artifact contains a private home-directory path, the bundle is withheld; edit the model and start a fresh run rather than changing saved evidence.

A completed stage cannot be overwritten. To retry, open a new example or upload the input again. Missing-evidence records distinguish unavailable logs or audits from successful checks.

The [capture manifest](onboarding/capture-manifest.json) describes historical interface screenshots. Those images illustrate navigation and are not evidence of a build or proof check for the current source revision. Read [limitations](limitations.md) for the supported scope and assumptions.
