# VAKE source consistency report

This report records corrections and remaining limitations in the 0.2.0 source consistency revision. The review covers the supplied source package, documentation, workflow scripts, browser service, formal module references, examples, and source manifests.

## Corrected issues

| Area | Finding | Correction |
|---|---|---|
| Lean library and export paths | Public CLI naming differed from the internal Lean library, namespace, certificate names, and generated paths. | The library, module tree, imports, declarations, templates, exporter, importer, audits, trace references, tests, and ignore rules now use VAKE consistently. |
| Environment settings | Scripts and CLI retained legacy aliases, making the public interface inconsistent. | Removed legacy aliases and documented the supported `VAKE_*` settings. |
| Package version | The Lean package metadata was still `0.1.0`, while the Rust package was `0.2.0`. | Aligned Lean metadata to `0.2.0`. |
| Source distribution | Git metadata retained historical project identifiers and was included in the supplied archive. | Clean packaging excludes `.git`, build caches, generated workspaces, and local run directories. |
| Documentation | The README and guides linked to absent provenance/setup files and referred to absent release reports. | Replaced those references with guides and reports included in this package. |
| Documentation perspective | Several documents described a delivery or handoff process rather than the tool's behavior for users. | Rewrote the README, usage, scope, examples, contribution, licensing, and release documentation as maintainer-to-user material. |
| Component inventory | The extraction inventory mixed earlier hashes and paths with current files, including conflicting destination mappings. | Replaced it with `docs/components.json`, generated from current component bytes by `scripts/component_manifest.py`. |
| Preflight | Source hygiene depended on `git ls-files` and could not run in a clean ZIP. | Added an archive mode using the packaging inclusion rules. Added identity checks and component/source-manifest hash validation. |
| Proof counts | The browser guide presented fixed declaration counts as if they applied to every run. | The guide now explains route-dependent inventories and refers to the current run's recorded audits. |
| Screenshots | Historical completed-run screenshots could be mistaken for current validation or intermediate-stage evidence. | Marked the images and capture manifest as historical illustrations; corrected the model-view caption. Their original image bytes are preserved. |
| Verification isolation | Isolated verification copied previously generated demonstration/audit files from the source tree. | Excluded demonstration modules, audit modules, and the generated signature-observation file. |
| Packaging | The generated `SignatureObservations.lean` file could enter a source package. | Excluded it from packaging, Git tracking rules, and Docker context rules. |
| Reproduction tool settings | Selected tools were local variables and were not always propagated into child workflows; Rust version reporting used a fixed command. | Propagated Cargo/Lake selections and added `VAKE_RUSTC` for the compiler and version reporting. Demo-only reproduction no longer unnecessarily requires Cargo. |
| Evidence path normalization | A bare `VAKE_LAKE=lake` setting could replace the substring in filenames such as `lake-manifest.json`. | Normalize bare tool names only when the entire value is the tool name; retain surrounding filename text. |
| Measurement validation | The measurement runner checked exit codes but did not confirm expected result statuses, and an early failure left no final summary. | Check both exit code and expected status; retain a `FAIL` summary and available logs on launch, output, or workflow failure. |

## Remaining limitations and review items

| Location | Current behavior | Consequence |
|---|---|---|
| `src/main.rs`, `src/lean_export.rs` | Initial profile version/interpretation failures report `UNSUPPORTED`; deeper profile validation failures can surface as `TRANSLATION_ERROR`. | Status classification is not uniform. Inspect the diagnostic. The README documents both routes; this revision does not refactor Rust error types. |
| `src/profile.rs`, `lean/VAKE/Symbolic.lean` | Credential validation checks key owners against setup parties but permits repeated credential records. The `credential` operation requires exactly one matching record; `credential_resolve` selects by index from matching records. | Duplicate records can make an otherwise admitted profile produce `invalid` for credential lookup. Preserve intentional indexed alternatives and avoid accidental exact duplicates; a stronger admission policy needs a separate contract decision. |
| `scripts/validate_lean.py` | Theorem inventory extraction uses a line-oriented reader for explicit namespace and theorem declarations. | It supports the current modules. Nested namespaces or substantially different declaration formatting need a corresponding parser change and tests. |
| `lean/VAKE/Symbolic.lean`, `lean/VAKE/Network.lean`, `lean/VAKE/EDHOC.lean` | The formal library retains branches for KEMTLS and EDHOC interpretations, but the Rust admission layer accepts only `restricted_symbolic_v1`. | The presence of those formal definitions does not enable those protocols through the CLI. Removing them would require a separate dependency and proof review. |
| `scripts/import_model.py`, `src/lean_export.rs` | Import and export are independently implemented programs. Concrete binding certificates check each exported instance. | There is no universal verified-compiler claim. Frontend acceptance alone does not guarantee every supported-model combination will complete Lean verification. |
| `scripts/verify.py`, `scripts/trace_demo.py` | Concrete terminal/global demonstrations use bundled example definitions and are restricted by their workflow or by the resulting certificate checks. | They are example-specific results. Custom models use the general correspondence route. |
| `scripts/measure.py` | Timings include subprocess startup and fresh Lean workspaces; OS caching is uncontrolled and peak memory is not collected. | Report the methodology with timing results. A failed workflow's partial summary is incomplete. |
| `LICENSE` | The supplied package does not establish authoritative notices or a complete distribution license. | Licensing remains unresolved; this revision grants no license. |
| Documentation screenshots | They are earlier UI captures, not executions of this revised source. | Obtain new run evidence before making validation claims about this revision. |

## Validation coverage

The review completed 24 toolchain-independent regression checks, Python syntax compilation, shell syntax checks, JavaScript syntax checks, static Lean import/inventory checks, and clean-archive preflight. Machine-readable coverage is in [validation.json](validation.json). All 16 checked-in Lean sources retain their original definitions and statements apart from namespace/import renaming. The regression checks cover Python proof-audit parsing, archive preflight and manifest tampering, environment settings, measurement failure reporting, evidence normalization, browser storage and HTTP guards, and shell startup outside the repository.

Rust/Cargo, Lean/Lake, Docker, and PowerShell are unavailable in the review environment. Rust compilation, frontend tests, actual Lean kernel checks, full end-to-end reproduction, container builds, and Windows execution therefore require a subsequent run with the pinned tools. This report does not present historical screenshots or simulated process results as proof execution.

Run the complete validation in a toolchain-equipped environment:

```bash
VAKE_UI_TEST_LEAN=1 python3 scripts/reproduce.py --stage all
python3 scripts/repository_preflight.py
```

The package's `source-manifest.json` identifies the delivered bytes. New execution results should identify those source bytes and retain their model/profile hashes, commands, raw logs, result statuses, and proof audits.
