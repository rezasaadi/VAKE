use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};
use vake::{check, contracts, lean_export, parse_model};

const NONCE: &[u8] = include_bytes!("../examples/nonce_exchange.json");
const MESSAGE: &[u8] = include_bytes!("../examples/public_message.json");
const PROFILE: &[u8] = include_bytes!("../examples/restricted_symbolic_v1.profile.json");
static NEXT: AtomicU64 = AtomicU64::new(0);

fn example(relative: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("examples")
        .join(relative)
}
fn scratch(label: &str) -> PathBuf {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("target/test-artifacts")
        .join(format!(
            "{label}-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    assert!(!path.exists(), "test output must be fresh");
    path
}
fn model_value() -> Value {
    serde_json::from_slice(MESSAGE).unwrap()
}
fn parse_value(value: &Value) -> vake::ir::Model {
    parse_model(&serde_json::to_vec(value).unwrap()).unwrap()
}
fn cli(args: &[&str]) -> (i32, Value) {
    let output = Command::new(env!("CARGO_BIN_EXE_vake"))
        .args(args)
        .output()
        .unwrap();
    let value = serde_json::from_slice(&output.stdout).unwrap_or_else(|err| {
        panic!(
            "CLI did not emit JSON: {err}\nstdout={}\nstderr={}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    });
    (output.status.code().unwrap(), value)
}

#[test]
fn original_nonce_example_is_closed_typed_and_backend_supported() {
    let model = parse_model(NONCE).unwrap();
    let report = check::check(&model).unwrap();
    assert!(report.closed);
    assert_eq!((report.roles, report.blocks, report.values), (2, 4, 6));
    contracts::contracts(&model).unwrap();
    assert_eq!(model.protocol.id, "VAKE.NonceExchange");
}

#[test]
fn metadata_defaults_do_not_relax_required_operational_fields() {
    let model = parse_model(MESSAGE).unwrap();
    assert!(check::check(&model).unwrap().closed);
    let mut missing_nullable = model_value();
    missing_nullable["types"][0]
        .as_object_mut()
        .unwrap()
        .remove("primitive_ref");
    let err = parse_model(&serde_json::to_vec(&missing_nullable).unwrap()).unwrap_err();
    assert!(err.contains("primitive_ref"), "{err}");
    let mut unknown = model_value();
    unknown["roles"][0]["blocks"][0]["terminator"]["silently_ignore"] = json!(true);
    let err = parse_model(&serde_json::to_vec(&unknown).unwrap()).unwrap_err();
    assert!(err.contains("unknown field"), "{err}");
}

#[test]
fn malformed_and_duplicate_nested_json_are_rejected_before_typed_decoding() {
    let malformed = fs::read(example("negative/malformed_syntax.json")).unwrap();
    assert!(parse_model(&malformed).is_err());
    let duplicate = fs::read(example("negative/duplicate_nested_key.json")).unwrap();
    let err = parse_model(&duplicate).unwrap_err();
    assert!(err.contains("duplicate JSON key: value"), "{err}");

    let nested = String::from_utf8(MESSAGE.to_vec()).unwrap().replace(
        "\"value\": \"hello\"",
        "\"value\": {\"nested\": {\"a\": 1, \"a\": 2}}",
    );
    let err = parse_model(nested.as_bytes()).unwrap_err();
    assert!(err.contains("duplicate JSON key: a"), "{err}");
}

#[test]
fn negative_type_fixtures_report_the_actual_failure() {
    for (file, expected) in [
        ("duplicate_declaration", "duplicate types: Bytes"),
        ("undefined_variable", "unknown values: neverDeclared"),
        ("type_mismatch", "type mismatch: expected Bytes, got Bool"),
        ("invalid_cfg", "unknown blocks: missingBlock"),
    ] {
        let model =
            parse_model(&fs::read(example(&format!("negative/{file}.json"))).unwrap()).unwrap();
        let err = check::check(&model).unwrap_err();
        assert!(err.contains(expected), "{file}: {err}");
    }
}

#[test]
fn unsupported_contracts_are_distinct_from_language_type_errors() {
    for (file, expected) in [
        (
            "invalid_crypto_contract",
            "backend signature/mode/family mismatch",
        ),
        ("unsupported_law", "unsupported primitive operation"),
    ] {
        let model =
            parse_model(&fs::read(example(&format!("negative/{file}.json"))).unwrap()).unwrap();
        check::check(&model).unwrap();
        let err = contracts::contracts(&model).unwrap_err();
        assert!(err.contains(expected), "{file}: {err}");
    }
}

#[test]
fn erased_local_cannot_be_read_but_existing_record_alias_remains_legal() {
    let mut model: Value = serde_json::from_slice(NONCE).unwrap();
    let steps = model["roles"][0]["blocks"][0]["steps"]
        .as_array_mut()
        .unwrap();
    steps.push(json!({
        "kind": "emit", "event_name": "AfterErase",
        "args": [{"kind": "ref", "value_id": "nonceA"}], "visibility": "local"
    }));
    let err = check::check(&parse_value(&model)).unwrap_err();
    assert!(
        err.contains("nonceA has no dominating live definition"),
        "{err}"
    );

    model["roles"][0]["blocks"][0]["steps"][5]["args"][0] = json!({
        "kind": "project", "record": {"kind": "ref", "value_id": "packetA"}, "field": "nonce"
    });
    check::check(&parse_value(&model)).unwrap();

}

#[test]
fn branch_merge_requires_definition_on_every_path() {
    let mut model = model_value();
    model["roles"][0]["entry_block"] = json!("start");
    model["roles"][0]["blocks"] = json!([
        {"id":"start","steps":[],"terminator":{"kind":"branch","condition":{"kind":"literal","type_id":"Bool","value":true},"true_block":"defined","false_block":"undefined"}},
        {"id":"defined","steps":[{"kind":"assign","output_value_id":"message","term":{"kind":"literal","type_id":"Bytes","value":"hello"}}],"terminator":{"kind":"jump","target_block":"join"}},
        {"id":"undefined","steps":[],"terminator":{"kind":"jump","target_block":"join"}},
        {"id":"join","steps":[{"kind":"send","bytes":{"kind":"ref","value_id":"message"},"channel_id":"publicChannel"}],"terminator":{"kind":"stop","reason":"done"}}
    ]);
    let err = check::check(&parse_value(&model)).unwrap_err();
    assert!(
        err.contains("message has no dominating live definition"),
        "{err}"
    );
}

#[test]
fn export_is_deterministic_preserves_original_inputs_and_does_not_claim_proof() {
    let left = scratch("export-left");
    let right = scratch("export-right");
    let first = lean_export::export(NONCE, PROFILE, &left).unwrap();
    let second = lean_export::export(NONCE, PROFILE, &right).unwrap();
    assert_eq!(first, second);
    assert_eq!(first["theorem_status"], "not_checked_by_export_command");
    assert_eq!(first["security_properties"], "open");
    assert_eq!(fs::read(left.join("model.json")).unwrap(), NONCE);
    assert_eq!(
        fs::read(left.join("operational-profile.json")).unwrap(),
        PROFILE
    );
    for file in first["files"].as_array().unwrap() {
        let relative = file["path"].as_str().unwrap();
        assert_eq!(
            fs::read(left.join(relative)).unwrap(),
            fs::read(right.join(relative)).unwrap(),
            "{relative}"
        );
    }
    let map: Value =
        serde_json::from_slice(&fs::read(left.join("source-map.json")).unwrap()).unwrap();
    assert!(
        map["locations"]
            .as_array()
            .is_some_and(|locations| !locations.is_empty())
    );
}

#[test]
fn export_failure_does_not_create_partial_output_or_overwrite_existing_files() {
    let unsupported_profile = fs::read(example("negative/unsupported_profile.json")).unwrap();
    let absent = scratch("bad-profile");
    assert!(lean_export::export(NONCE, &unsupported_profile, &absent).is_err());
    assert!(!absent.exists());

    let duplicate = String::from_utf8(PROFILE.to_vec()).unwrap().replace(
        "\"kem_correctness\": \"ideal\"",
        "\"kem_correctness\": \"ideal\", \"kem_correctness\": \"may_fail\"",
    );
    let absent = scratch("duplicate-profile");
    let err = lean_export::export(NONCE, duplicate.as_bytes(), &absent).unwrap_err();
    assert!(err.contains("duplicate JSON key"), "{err}");
    assert!(!absent.exists());

    let existing = scratch("existing");
    fs::create_dir_all(&existing).unwrap();
    fs::write(existing.join("keep.txt"), "existing user content").unwrap();
    let err = lean_export::export(NONCE, PROFILE, &existing).unwrap_err();
    assert!(err.contains("absent or empty"), "{err}");
    assert_eq!(
        fs::read_to_string(existing.join("keep.txt")).unwrap(),
        "existing user content"
    );
    assert_eq!(fs::read_dir(&existing).unwrap().count(), 1);
}

#[test]
fn cli_reports_checked_parse_type_and_unsupported_statuses() {
    let (code, report) = cli(&["check", example("nonce_exchange.json").to_str().unwrap()]);
    assert_eq!(code, 0);
    assert_eq!(report["status"], "CHECKED");
    assert_eq!(report["proof_status"], "NOT_CHECKED");
    for (file, status) in [
        ("malformed_syntax", "PARSE_ERROR"),
        ("duplicate_nested_key", "PARSE_ERROR"),
        ("unknown_instruction", "PARSE_ERROR"),
        ("duplicate_declaration", "TYPE_ERROR"),
        ("undefined_variable", "TYPE_ERROR"),
        ("type_mismatch", "TYPE_ERROR"),
        ("invalid_cfg", "TYPE_ERROR"),
        ("invalid_crypto_contract", "UNSUPPORTED"),
        ("unsupported_law", "UNSUPPORTED"),
    ] {
        let path = example(&format!("negative/{file}.json"));
        let (code, report) = cli(&["check", path.to_str().unwrap()]);
        assert_eq!(code, 1, "{file}: {report}");
        assert_eq!(report["status"], status, "{file}: {report}");
        assert_eq!(report["security_conclusion"], "none");
    }
}

#[test]
fn cli_open_model_is_an_obligation_and_not_successful_verification() {
    let mut model = model_value();
    model["holes"] = json!([{
        "id":"missingPayload", "object_path":"/roles/0/blocks/0/steps/0/term",
        "expected_type_id":"Bytes", "reason":"Source payload is intentionally unspecified",
        "blocked_obligation_ids":[]
    }]);
    model["roles"][0]["blocks"][0]["steps"][0]["term"] = json!({
        "kind":"hole", "hole_id":"missingPayload", "type_id":"Bytes"
    });
    let dir = scratch("open-model");
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("open.json");
    fs::write(&path, serde_json::to_vec(&model).unwrap()).unwrap();
    let (code, report) = cli(&["check", path.to_str().unwrap()]);
    assert_eq!(code, 2);
    assert_eq!(report["status"], "OPEN_OBLIGATION");
    assert_eq!(report["proof_status"], "NOT_CHECKED");
    assert_eq!(report["kernel"]["holes"], json!(["missingPayload"]));
}

#[test]
fn cli_export_requires_explicit_supported_profile_and_reports_only_export() {
    let model = example("nonce_exchange.json");
    let profile = example("restricted_symbolic_v1.profile.json");
    let out = scratch("cli-export");
    let (code, report) = cli(&[
        "export",
        model.to_str().unwrap(),
        "--profile",
        profile.to_str().unwrap(),
        "--out",
        out.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "{report}");
    assert_eq!(report["status"], "EXPORTED");
    assert_eq!(report["proof_status"], "NOT_CHECKED");
    let missing = scratch("cli-missing-profile");
    let (code, report) = cli(&[
        "export",
        model.to_str().unwrap(),
        "--out",
        missing.to_str().unwrap(),
    ]);
    assert_eq!(code, 1);
    assert_eq!(report["status"], "UNSUPPORTED");
    assert!(!missing.exists());
    let unsupported = example("negative/unsupported_profile.json");
    let absent = scratch("cli-unsupported-profile");
    let (code, report) = cli(&[
        "export",
        model.to_str().unwrap(),
        "--profile",
        unsupported.to_str().unwrap(),
        "--out",
        absent.to_str().unwrap(),
    ]);
    assert_eq!(code, 1);
    assert_eq!(report["status"], "UNSUPPORTED");
    assert!(!absent.exists());
}
