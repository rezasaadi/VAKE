# VAKE

VAKE (Verification-Assisted Key Establishment) is a research tool for checking typed protocol models and their translation into Lean 4. It accepts JSON models, checks their syntax and types, exports a formal target representation, and asks Lean to check source/target bindings and operational correspondence certificates.

Use the browser interface to follow a model through six steps: **open a model, check it, create Lean files, run Lean, inspect execution, and save evidence**. The same checks are available from the command line.

**Start with the [guided walkthrough](docs/start-here.md).**

![VAKE workspace](docs/onboarding/welcome.jpg)

The image illustrates the interface. Screenshots are historical UI captures; run the checks locally to obtain evidence for this source version.

## What VAKE checks

| Stage | Result | Meaning |
|---|---|---|
| Model check | `CHECKED` | The JSON model passed parsing, nominal type checking, control-flow checks, and supported-operation admission. |
| Export | `EXPORTED` | Lean files and hash-addressed evidence were generated. The export command does not check proofs. |
| Lean verification | `PROVED_UNDER_ASSUMPTIONS` | Lean checked the concrete source/target bindings and selected correspondence certificates under the reported assumptions. |
| Bundled execution checks | `PROVED_UNDER_ASSUMPTIONS` | Lean checked particular executions of the exact bundled nonce model and profile. |
| Altered-binding controls | `PASSED` | Two altered bindings were rejected at their expected checks. |

These results concern formal modeling and translation. VAKE does not currently prove authentication, secrecy, replay resistance, computational security, or post-quantum security, and it does not perform general attack search. The Rust frontend and independent Python importer remain trusted programs. See [scope and limitations](docs/limitations.md).

## Run with Docker

Install Docker with Compose, extract the archive, and open a terminal in the `VAKE` directory:

```bash
docker compose build
docker compose up -d
```

Open **http://127.0.0.1:8765** and select **Take a guided tour**. The image build installs the pinned tools and runs the reproduction workflow. The first build needs internet access to download the base image, Lean, and Rust dependencies.

```bash
docker compose logs --tail=50
docker compose down
```

Reports persist in the `vake-reports` volume when the container stops. To rerun the workflow in the container:

```bash
docker compose run --rm vake reproduce
```

The service is local and unauthenticated. Compose publishes the port on host loopback. See the [Docker guide](docs/docker.md) for report export and troubleshooting.

## Installation

For a native installation, use the versions pinned in the source:

| Dependency | Version | Purpose |
|---|---|---|
| Rust / Cargo | 1.97.1 | Build and test the frontend and CLI |
| Lean / Lake | 4.34.1 | Compile modules and check certificates |
| Python | 3.10 or newer | Import models independently, run workflows, and serve the browser UI |

Python workflows use the standard library. No `pip install` step is required. Install Rustup and Elan before using the toolchain helpers; the helpers install the pinned compiler versions, not those managers.

On Linux or macOS, from the repository root:

```bash
bash scripts/install-toolchains.sh
python3 scripts/reproduce.py --stage build
python3 -m ui.server --port 8765 --open
```

On Windows, from PowerShell:

```powershell
.\scripts\install-toolchains.ps1
.\scripts\build.ps1
.\scripts\run-ui.ps1 -Port 8765 -Open
```

If the toolchains are already installed, skip the installation helper. Check `cargo --version`, `rustc --version`, and, from `lean/`, `lake env lean --version`. Keep the binary with the repository's scripts, Lean files, and examples. An executable copied elsewhere needs `VAKE_ROOT` pointing to this repository.

## Use the command line

The following commands run from the repository root. Use `target\debug\vake.exe` instead of `./target/debug/vake` on Windows.

```bash
./target/debug/vake --version
./target/debug/vake --help
./target/debug/vake check examples/nonce_exchange.json
```

Export requires an explicit profile and a fresh output directory:

```bash
./target/debug/vake export examples/nonce_exchange.json \
  --profile examples/restricted_symbolic_v1.profile.json \
  --out reports/nonce-export
```

For export followed by independent import and Lean verification:

```bash
./target/debug/vake verify examples/nonce_exchange.json \
  --profile examples/restricted_symbolic_v1.profile.json \
  --out reports/nonce-verify
```

Use different output directories for these commands. Export accepts an absent or empty directory; verification creates an isolated Lean workspace and requires a fresh verification run. Omitting `--out` for `verify` creates a unique directory under `reports/runs/`.

The general `verify` command checks correspondence. To run the bundled local certificate, both global trace scenarios, binding controls, and the signature-construction example, use:

```bash
./target/debug/vake demo
```

### Exit codes and diagnostics

CLI results are JSON. `check`, `export`, and `verify` return `0` on successful completion and `1` on rejection or failure. `check` and `verify` return `2` for a model with unresolved holes; export can succeed for such a model without checking a proof. `demo` prints a workflow summary with `PASS` or `FAIL`.

| Status | Next step |
|---|---|
| `PARSE_ERROR` | Fix malformed JSON, duplicate keys, unknown fields, or unknown variants. |
| `TYPE_ERROR` | Fix the reported declaration, reference, type, or control-flow error. |
| `UNSUPPORTED` | Use supported model operations and the supported profile. |
| `OPEN_OBLIGATION` | Resolve model holes, or inspect the failed certificate diagnostic. The surrounding command and exit code distinguish these cases. |
| `TRANSLATION_ERROR` | Inspect the export or independent-import diagnostic; it can also include profile validation failures. |
| `INCONCLUSIVE` / `INTERNAL_ERROR` | Inspect logs for missing tools, interrupted processes, timeouts, or execution errors. |

A model with holes can be exported but cannot receive a closed-model verification result. A nonzero result is never a security conclusion.

## Work with a model

Start from one of the [bundled examples](examples/README.md):

| File | Purpose |
|---|---|
| `examples/public_message.json` | Minimal public-message model for learning the schema |
| `examples/nonce_exchange.json` | Two-role model used by the guided tour and concrete execution certificates |
| `examples/signature_check.json` | Symbolic signature construction and separate executable verification observations |
| `examples/restricted_symbolic_v1.profile.json` | Profile used by the bundled models |
| `examples/negative/` | Inputs that illustrate parsing, typing, control-flow, contract, and profile rejection |

The model schema is `format_version: "0.1"`; the operational profile uses `schema_version: "1.0"` and `interpretation: "restricted_symbolic_v1"`. The supported codec, `fixture_tlv`, is symbolic and does not implement a binary wire format. Read the [input-language guide](docs/language.md) before adding operations or changing types.

The browser accepts model and profile text up to 2 MiB each. Each run keeps an immutable input copy. The nonce-specific trace and terminal checks require the exact bundled model/profile bytes; editing or reformatting either input disables those checks while leaving the general correspondence route available.

## Saved evidence

Browser runs live under `reports/ui-runs/`; reproduction and demo runs live under `reports/runs/`. A browser evidence ZIP contains the saved input, generated Lean source, stage commands and outputs, available proof audits, and a hash manifest. Completed stage results are retained; use a new run to retry a stage.

`export-manifest.json` identifies the model/profile bytes and exported files. `verification-result.json` records certificate scope, commands, assumptions, and failures. `proof-audit.json` records named declarations and their logical axiom dependencies. Declaration counts are inventories, not counts of cryptographic security properties.

Downloading an idle, unfinished run preserves its current state. Wait for an active stage to finish before downloading. Metadata paths are normalized in the shared ZIP; model and Lean bytes remain unchanged. The [browser reference](docs/ui-user-guide.md) explains the evidence fields.

## Reproduce and maintain the source

Run all build, test, audit, and demonstration stages:

```bash
VAKE_UI_TEST_LEAN=1 python3 scripts/reproduce.py --stage all
```

On Windows:

```powershell
$env:VAKE_UI_TEST_LEAN='1'
.\scripts\reproduce.ps1
```

`--stage build`, `--stage test`, and `--stage demo` select individual workflows. Add `--offline` after dependencies are cached to prevent Cargo downloads; Lean remains required. The GitHub workflow invokes the full reproduction and collects normalized logs.

Check source naming, documentation links, and manifest hashes in either a Git checkout or an extracted source ZIP:

```bash
python3 scripts/repository_preflight.py
```

Package a clean ZIP outside the repository:

```bash
python3 scripts/package.py --out ../VAKE-source.zip
```

The package excludes Git history, build caches, generated Lean workspaces, and local run directories. Its `source-manifest.json` records the included file bytes and hashes. After changing a listed component, refresh `docs/components.json` with `python3 scripts/component_manifest.py` before running preflight.

### Optional environment settings

| Variable | Use |
|---|---|
| `VAKE_ROOT` | Repository path used by a relocated CLI executable |
| `VAKE_PYTHON` | Python executable used by CLI and shell wrappers |
| `VAKE_CARGO` | Cargo executable used by the reproducer |
| `VAKE_RUSTC` | Rust compiler executable used by reproduction and version reporting |
| `VAKE_LAKE` | Lake executable used by verification workflows |
| `VAKE_UI_TEST_LEAN` | Set to `1` to include real Lean integration tests |
| `VAKE_UI_TEST_TIMEOUT` | Per-stage timeout used by UI tests |

## Troubleshooting

- **Missing tools:** add the pinned tools to PATH or set the corresponding environment variable. Native UI startup does not build the CLI.
- **Output directory already exists:** choose a fresh directory rather than mixing evidence from different runs.
- **Port already in use:** stop the existing server or run `python3 -m ui.server --port 0 --open` for an available port.
- **A check fails:** open its command result and read stdout/stderr. The first failure is usually more useful than the final summary.
- **A custom model has no trace button:** the concrete trace demonstrations are restricted to the exact bundled nonce model/profile.

For current source-review findings and validation coverage, see [the consistency report](docs/consistency-report.md). Licensing information is in [LICENSE](LICENSE). Contributions and bug reports are covered in [CONTRIBUTING.md](CONTRIBUTING.md).
