# Contributing

For a bug report, include the model, profile, command, tool versions, and actual diagnostic. For browser failures, include the stage's stdout and stderr. Remove private input before sharing evidence.

Keep model acceptance, export, certificate checks, and protocol security claims distinct. Changes to formal definitions or theorem statements need mathematical review.

Run the [reproduction workflow](README.md#cli-and-reproduction) after execution or proof changes. After source changes, run `python3 scripts/prepare_release.py` to refresh both manifests and check the complete working tree. Commit all changed and new source files together with both manifests. Run `python3 scripts/prepare_release.py --check-publication` before pushing to check for pending files. CI checks the committed checkout without regenerating its manifests.

Keep compiler caches and local runs outside the source package. Evidence bundles preserve model and Lean bytes; machine paths are normalized only in metadata copies.

Contributions are accepted under the [Apache License 2.0](LICENSE).
