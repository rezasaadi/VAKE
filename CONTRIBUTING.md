# Contributing

For a bug report, include the model, profile, command, tool versions, and actual diagnostic. For browser failures, include the stage's stdout and stderr. Remove private input before sharing evidence.

Keep model acceptance, export, certificate checks, and protocol security claims distinct. Changes to formal definitions or theorem statements need mathematical review.

Run the [reproduction workflow](README.md#cli-and-reproduction) after execution or proof changes. After source changes, refresh `docs/components.json` with `python3 scripts/component_manifest.py` and run `python3 scripts/repository_preflight.py`. Check a packaged ZIP with the same preflight command.

Keep compiler caches and local runs outside the source package. Evidence bundles preserve model and Lean bytes; machine paths are normalized only in metadata copies.

See [LICENSE](LICENSE) for licensing status.
