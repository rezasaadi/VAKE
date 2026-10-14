# VAKE

**[Start here: take the guided tour](docs/start-here.md)**

VAKE checks typed JSON protocol models, exports Lean representations, and checks correspondence and concrete execution certificates. The local browser interface saves each run's inputs, generated files, commands, and evidence.

![VAKE workspace](docs/onboarding/welcome.jpg)

The screenshots show an earlier interface state. Run the checks locally for evidence of this source version.

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

## Examples and scope

- **Nonce exchange:** honest execution and malformed-message rejection.
- **DH exchange:** honest key agreement and a concrete man-in-the-middle execution.
- **Signed DH:** honest key agreement and rejection of the two supplied share substitutions.
- **Signature construction:** a concrete primitive lemma and separately labelled executable observations.

Execution certificates come from [scenario files](docs/scenarios.md) bound to the exact model/profile bytes. Failed certificates report `CERTIFICATE_FAILED`; invalid scenario files report `SCENARIO_ERROR`.

These are checked instances under reported symbolic and logical assumptions. They do not establish universal authentication, secrecy, replay resistance, computational security, or post-quantum security. The execution checks use the reused formal library with structural value keys and deducibility proof search.

Redistribution licensing remains unresolved; see [LICENSE](LICENSE).

- [Input language](docs/language.md)
- [Examples](examples/README.md)
- [Browser reference](docs/ui-user-guide.md)
- [Limitations](docs/limitations.md)
