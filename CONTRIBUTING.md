# Contributing to VAKE

Include the model, operational profile, exact command, tool versions, expected result, and actual diagnostic in a bug report. For browser issues, include the failing stage and its saved stdout/stderr. Remove private input and machine-specific information before sharing evidence.

Keep frontend acceptance, file export, certificate checks, and protocol security claims distinct. A change to the exporter or importer must preserve the relationship between the original model and generated target. A change to formal semantics or theorem statements needs its own mathematical review.

Use VAKE consistently in module names, paths, commands, and documentation. Documentation should address the person installing or using the tool and describe behavior present in the source. Do not assert a successful check without its execution evidence.

Run the [reproduction workflow](README.md#reproduce-and-maintain-the-source) after code or proof changes. Refresh the component manifest with `python3 scripts/component_manifest.py`, then run `python3 scripts/repository_preflight.py` after source or documentation changes. Extract a packaged ZIP and repeat preflight to check the files users will receive. Regression tests should check the affected behavior.

Generated certificates, compiler caches, and local run directories belong outside the source package. Preserve model and proof bytes in evidence bundles; normalize machine paths only in metadata copies.

See [LICENSE](LICENSE) for the current licensing status.
