# VAKE

**[Start here: take the guided tour](docs/start-here.md)**

VAKE checks typed JSON protocol models, exports Lean representations, and checks correspondence and concrete execution certificates. The local browser interface saves each run's inputs, generated files, commands, and evidence.

![VAKE workspace](docs/onboarding/welcome.jpg)

Screenshots show an older interface; run the checks locally for current results.

## Run with Docker

```bash
docker compose build
docker compose up -d
```

Enter **http://127.0.0.1:8765** in your browser's address bar and select **Take a guided tour**. Stop with `docker compose down`; reports persist in the named volume. See the [Docker guide](docs/docker.md).

## Native installation

Install Rust 1.97.1, Lean 4.34.1 with Lake, and Python 3.10 or newer. Python workflows use the standard library.

```bash
python3 scripts/reproduce.py --stage build
python3 -m ui.server --port 8765
```

On Windows, run `.\scripts\build.ps1`, then `.\scripts\run-ui.ps1 -Port 8765 -Open`.

## CLI and reproduction

```bash
./target/debug/vake check examples/dh_exchange.json
./target/debug/vake verify examples/dh_exchange.json --profile examples/restricted_symbolic_v1.profile.json --out reports/dh-check
./target/debug/vake demo
VAKE_UI_TEST_LEAN=1 python3 scripts/reproduce.py --stage all
```

On Windows, use `target\debug\vake.exe`; set `$env:VAKE_UI_TEST_LEAN='1'` before running `.\scripts\reproduce.ps1`. The full demo checks the nonce, DH, signed-DH, signature-construction, and altered-binding examples. Use fresh output directories for verification runs.

## Prepare a source update

After editing source or documentation, run:

```bash
python3 scripts/prepare_release.py
```

This refreshes both hash manifests and checks the complete working tree. Include every changed and new source file, plus both manifests, in the same commit. Before pushing, run `python3 scripts/prepare_release.py --check-publication` to check for pending files. CI checks the committed snapshot; it saves preflight failures in the `vake-linux-evidence` artifact.

## Examples

- **Nonce exchange:** honest execution and malformed-message rejection.
- **DH exchange:** honest key agreement and a concrete man-in-the-middle execution.
- **Signed DH:** honest key agreement and rejection of the two bundled share substitutions.
- **Signature construction:** a concrete primitive lemma and separately labelled executable observations.

Execution certificates come from [scenario files](docs/scenarios.md) bound to the exact model/profile bytes. Failed certificates report `CERTIFICATE_FAILED`; invalid scenario files report `SCENARIO_ERROR`.

## What the checks establish

Each result is a kernel-checked certificate for the encoded model, under the symbolic contracts and the logical axioms listed in its audit. Concretely, VAKE checks:

- that the generated Lean target agrees with an independently imported source (a differential check of the Rust exporter against the Python importer; the translation itself is a constructor renaming);
- the listed final-state claims of each scenario execution, with a kernel-checked deducibility proof for every adversary step;
- the reusable correspondence theorems and the injectivity of the value key used for symbolic equality.

The checks cover particular executions, not all executions. They do not establish authentication, secrecy, replay resistance, computational security, or post-quantum security. See [Limitations](docs/limitations.md) for the full trust boundary.

Verification runs reuse the compiled Lean library from a content-addressed cache under `.vake-cache/`; set `VAKE_LEAN_CACHE=0` to rebuild it from source.

## Documentation

- [Input language](docs/language.md)
- [Examples](examples/README.md)
- [Scenario files](docs/scenarios.md)
- [Browser reference](docs/ui-user-guide.md)
- [Limitations](docs/limitations.md)

## License

VAKE is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).
