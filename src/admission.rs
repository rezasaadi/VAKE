use crate::{ir::Model, transport};
use serde_json::{json, Value};
fn default(v: &mut Value, key: &str, value: Value) {
    if let Some(object) = v.as_object_mut() {
        object.entry(key).or_insert(value);
    }
}
fn provenance(v: &mut Value) {
    default(
        v,
        "provenance",
        json!({"kind":"constructed","source_refs":[],
        "rationale":"Optional evidence metadata omitted in standalone input."}),
    );
}
pub fn normalize_metadata(value: &mut Value) {
    default(value, "source_ids", json!([]));
    default(
        value,
        "assessment",
        json!({"case_profile_id":"Standalone","obligation_ledger_id":"Unassessed"}),
    );
    if let Some(protocol) = value.get_mut("protocol") {
        default(protocol, "case_kind", json!("syntax_example"));
        default(protocol, "pinned_source_ids", json!([]));
        default(
            protocol,
            "fragment_description",
            json!("Standalone protocol model"),
        );
        provenance(protocol);
    }
    for category in [
        "types",
        "primitives",
        "constructors",
        "encodings",
        "values",
        "slots",
        "messages",
        "contexts",
        "roles",
        "targets",
        "holes",
    ] {
        if let Some(items) = value.get_mut(category).and_then(Value::as_array_mut) {
            for item in items {
                provenance(item);
                if category == "primitives" {
                    default(item, "security_assumption_ids", json!([]));
                    default(item, "cost_category", json!("unknown"));
                    default(item, "cost_evidence_refs", json!([]));
                }
                if category == "values" {
                    default(item, "intended_visibility", json!("unspecified"));
                }
                if category == "roles" {
                    if let Some(blocks) = item.get_mut("blocks").and_then(Value::as_array_mut) {
                        for block in blocks {
                            provenance(block);
                            if let Some(steps) =
                                block.get_mut("steps").and_then(Value::as_array_mut)
                            {
                                for step in steps {
                                    provenance(step);
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

pub fn parse_model(bytes: &[u8]) -> Result<Model, String> {
    transport::unique(bytes).map_err(|e| format!("model: {e}"))?;
    let mut value: Value = serde_json::from_slice(bytes).map_err(|e| format!("model: {e}"))?;
    normalize_metadata(&mut value);
    serde_json::from_value(value).map_err(|e| format!("model: {e}"))
}
