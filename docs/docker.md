# Run VAKE with Docker

## Start and stop

With Docker and Compose installed, run from the repository root:

```bash
docker compose build
docker compose up -d
docker compose logs --tail=50
```

Open **http://127.0.0.1:8765**. Compose exposes the service on host loopback. The container runs as an unprivileged user; reports persist in the named `vake-reports` volume.

```bash
docker compose down
```

Stopping the container does not remove the reports volume. Keep the loopback port mapping because the local compiler API does not have authentication.

## Reproduce the checks

```bash
docker compose run --rm vake reproduce
```

The image build also runs the full reproducer, including the opt-in Lean integration tests. The recipe pins Rust 1.97.1 and Lean 4.34.1 and checks the Lean download against architecture-specific SHA-256 values. It installs Python 3 from the base image's distribution.

Builds need network access for the base image, Lean archive, and Cargo dependencies. Runtime reproduction uses cached Cargo dependencies with `--offline`. Native and container reports are under `reports/runs/` and `reports/ui-runs/`; inside the container those paths are beneath `/opt/vake/`.

The recipe supports amd64 and arm64 archive selection. That selection alone does not establish a successful build on either platform. Consult [the consistency report](consistency-report.md) for the checks performed on this source revision.

## Export reports

For a single run, use **Download evidence ZIP** in the browser. To copy all reports from a running Compose service to the host:

```bash
mkdir -p vake-reports-export
docker compose cp vake:/opt/vake/reports/. ./vake-reports-export/
```

On PowerShell, create the destination with `New-Item -ItemType Directory -Force vake-reports-export`, then use the same `docker compose cp` command. Exported reports are excluded from source packaging.

## Troubleshooting

- If `docker info` fails, start or repair the Docker engine.
- If a build fails, inspect the first failing command. An unavailable pinned image, download, or hash mismatch needs resolution before the reproduction gate can run.
- If the browser rejects a request, enter the localhost address directly; cross-origin requests are refused.
- If the host port is occupied, stop the other service or adjust the host port in Compose. Use the new port in the browser.
- If a verification stage fails, inspect its saved logs. The health check reports HTTP readiness, not certificate validity.

Continue with the [guided walkthrough](start-here.md) or [browser reference](ui-user-guide.md).
