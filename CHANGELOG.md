# Changelog

## 0.2.0 — source consistency update

- Unified the CLI, Lean library, generated certificates, script settings, tests, and packaging paths under VAKE.
- Expanded installation, command examples, model guidance, result interpretation, evidence handling, and troubleshooting in the README.
- Reworked documentation as user and contributor guides, repaired local links, and removed references to unavailable release reports.
- Replaced the stale extraction inventory with a current component manifest and a repeatable manifest generator.
- Added source-archive support, project-identity checks, and manifest validation to repository preflight.
- Isolated verification workspaces from generated audit and demonstration files.
- Propagated toolchain selections into child reproduction workflows and supported an explicit Rust compiler override.
- Tightened measurement result validation and recorded failed measurement workflows.

Validation coverage and remaining limitations for this revision are recorded in [the consistency report](docs/consistency-report.md). Historical interface screenshots illustrate the workflow and are not validation evidence for this revision.
