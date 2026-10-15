pub use crate::profile::OperationalProfile;
use crate::{check, contracts, ir::Model};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};
pub const TOOLCHAIN: &str = "leanprover/lean4:v4.34.1";
pub const VERSION: &str = "vake-export-v1";
pub fn raw_digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn quote(s: &str) -> String {
    let mut result = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            c if c.is_control() => result.push_str(&format!("\\u{:04x}", c as u32)),
            c => result.push(c),
        }
    }
    result.push('"');
    result
}
pub fn symbol(path: &str) -> String {
    format!(
        "dsl_{}",
        path.bytes().map(|b| format!("{b:02x}")).collect::<String>()
    )
}
fn list(items: impl IntoIterator<Item = String>) -> String {
    format!("[{}]", items.into_iter().collect::<Vec<_>>().join(", "))
}
fn tuple(items: impl IntoIterator<Item = String>) -> String {
    format!("({})", items.into_iter().collect::<Vec<_>>().join(", "))
}
fn structure(items: impl IntoIterator<Item = String>) -> String {
    format!("⟨{}⟩", items.into_iter().collect::<Vec<_>>().join(", "))
}
fn get<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().expect("typed input was validated")
}
fn q(v: &Value, key: &str) -> String {
    quote(get(v, key))
}
fn array<'a>(v: &'a Value, key: &str) -> &'a [Value] {
    v[key].as_array().expect("typed input was validated")
}
fn strings(v: &Value, key: &str) -> String {
    list(
        array(v, key)
            .iter()
            .map(|s| quote(s.as_str().expect("typed string"))),
    )
}
fn fields(v: &Value, key: &str) -> String {
    list(
        array(v, key)
            .iter()
            .map(|f| tuple([q(f, "name"), q(f, "type_id")])),
    )
}

#[derive(Default)]
struct Emitter {
    locations: Vec<Value>,
    symbols: Vec<Value>,
}
impl Emitter {
    fn mark(&mut self, path: &str, kind: &str) {
        self.locations.push(
            json!({"source_pointer":path,"syntax_kind":kind,"generated_symbol":symbol(path)}),
        );
    }
    fn name(&mut self, path: &str, id: &str) {
        self.symbols
            .push(json!({"source_pointer":path,"original":id,"lean_symbol":symbol(path)}));
    }
    fn term(&mut self, t: &Value, path: &str) -> String {
        self.mark(path, get(t, "kind"));
        match get(t, "kind") {
            "ref" => format!("(.load {})", q(t, "value_id")),
            "literal" => format!(
                "(.constant {} {})",
                q(t, "type_id"),
                quote(&t["value"].to_string())
            ),
            "record" => {
                let mut rest = ".nil".into();
                for (i, f) in array(t, "fields").iter().enumerate().rev() {
                    let expr = self.term(&f["term"], &format!("{path}/fields/{i}/term"));
                    rest = format!("(.cons {} {expr} {rest})", q(f, "name"));
                }
                format!("(.build {} {rest})", q(t, "constructor_id"))
            }
            "project" => format!(
                "(.select {} {})",
                self.term(&t["record"], &format!("{path}/record")),
                q(t, "field")
            ),
            "encode" => format!(
                "(.serialize {} {})",
                q(t, "encoding_id"),
                self.term(&t["record"], &format!("{path}/record"))
            ),
            "apply" => format!(
                "(.call {} {})",
                q(t, "primitive_id"),
                self.args(array(t, "args"), &format!("{path}/args"))
            ),
            "hole" => format!("(.unavailable {} {})", q(t, "hole_id"), q(t, "type_id")),
            _ => unreachable!("strict typed AST"),
        }
    }
    fn args(&mut self, args: &[Value], path: &str) -> String {
        let mut rest = ".nil".into();
        for (i, t) in args.iter().enumerate().rev() {
            rest = format!("(.cons {} {rest})", self.term(t, &format!("{path}/{i}")));
        }
        rest
    }
    fn step(&mut self, s: &Value, path: &str) -> String {
        self.mark(path, get(s, "kind"));
        match get(s, "kind") {
            "assign" => format!(
                "(.store {} {})",
                q(s, "output_value_id"),
                self.term(&s["term"], &format!("{path}/term"))
            ),
            "sample" => format!(
                "(.generate {} {})",
                q(s, "output_value_id"),
                q(s, "generator_id")
            ),
            "invoke" => format!(
                "(.execute {} {} {})",
                q(s, "primitive_id"),
                self.args(array(s, "args"), &format!("{path}/args")),
                q(s, "result_value_id")
            ),
            "receive" => format!("(.input {})", q(s, "output_bytes_value_id")),
            "send" => format!(
                "(.publish {} {})",
                self.term(&s["bytes"], &format!("{path}/bytes")),
                q(s, "channel_id")
            ),
            "read" => format!("(.fetch {} {})", q(s, "slot_id"), q(s, "output_value_id")),
            "write" => format!(
                "(.update {} {})",
                q(s, "slot_id"),
                self.term(&s["value"], &format!("{path}/value"))
            ),
            "erase" => format!("(.clear {})", q(s, "object_id")),
            "emit" => format!(
                "(.log {} {} {})",
                q(s, "event_name"),
                self.args(array(s, "args"), &format!("{path}/args")),
                q(s, "visibility")
            ),
            "accept" => {
                let peer = if s["peer"].is_null() {
                    "none".into()
                } else {
                    format!("(some {})", self.term(&s["peer"], &format!("{path}/peer")))
                };
                format!(
                    "(.commit {} {} {peer})",
                    q(s, "target_id"),
                    self.term(&s["key"], &format!("{path}/key"))
                )
            }
            "export" => format!(
                "(.output {} {})",
                q(s, "target_id"),
                self.term(&s["key"], &format!("{path}/key"))
            ),
            _ => unreachable!("strict typed AST"),
        }
    }
    fn end(&mut self, t: &Value, path: &str) -> String {
        self.mark(path, get(t, "kind"));
        match get(t, "kind") {
            "jump" => format!("(.goto {})", q(t, "target_block")),
            "branch" => format!(
                "(.choose {} {} {})",
                self.term(&t["condition"], &format!("{path}/condition")),
                q(t, "true_block"),
                q(t, "false_block")
            ),
            "match" => format!(
                "(.dispatch {} {})",
                q(t, "result_value_id"),
                list(array(t, "arms").iter().map(|a| {
                    structure([
                        q(a, "tag"),
                        list(
                            array(a, "bindings")
                                .iter()
                                .map(|b| tuple([q(b, "payload_name"), q(b, "value_id")])),
                        ),
                        q(a, "target_block"),
                    ])
                }))
            ),
            "stop" => format!("(.halt {})", q(t, "reason")),
            "reject" => format!("(.refuse {} {})", strings(t, "target_ids"), q(t, "reason")),
            _ => unreachable!("strict typed AST"),
        }
    }
    fn registry(&mut self, m: &Value, model: &Model) -> String {
        for category in [
            "types",
            "primitives",
            "constructors",
            "encodings",
            "values",
            "slots",
            "targets",
            "roles",
            "contexts",
            "messages",
            "holes",
        ] {
            for (i, v) in array(m, category).iter().enumerate() {
                self.name(&format!("/{category}/{i}/id"), get(v, "id"));
            }
        }
        structure([
            list(array(m, "types").iter().map(|t| {
                structure([
                    q(t, "id"),
                    q(t, "kind"),
                    strings(t, "parameters"),
                    fields(t, "fields"),
                    t["primitive_ref"]
                        .as_str()
                        .map(|p| format!("(some {})", quote(p)))
                        .unwrap_or("none".into()),
                ])
            })),
            list(
                array(m, "primitives")
                    .iter()
                    .zip(&model.primitives)
                    .map(|(p, typed)| {
                        structure([
                            q(p, "id"),
                            q(p, "family"),
                            q(p, "mode"),
                            quote(&contracts::operation(typed).expect("validated contract")),
                            q(p, "failure_profile"),
                            list(array(p, "inputs").iter().map(|i| {
                                tuple([q(i, "name"), q(i, "type_id"), q(i, "position_kind")])
                            })),
                            list(
                                array(p, "outcomes")
                                    .iter()
                                    .map(|o| tuple([q(o, "tag"), fields(o, "payload")])),
                            ),
                            strings(p, "law_ids"),
                        ])
                    }),
            ),
            list(
                array(m, "constructors")
                    .iter()
                    .map(|c| structure([q(c, "id"), q(c, "type_id"), fields(c, "fields")])),
            ),
            list(array(m, "encodings").iter().map(|c| {
                structure([
                    q(c, "id"),
                    q(c, "family"),
                    strings(c, "input_type_ids"),
                    strings(c, "contract_ids"),
                ])
            })),
            list(array(m, "values").iter().map(|v| {
                structure([
                    q(v, "id"),
                    q(v, "type_id"),
                    q(v, "owner_role"),
                    q(v, "storage_kind"),
                ])
            })),
            list(array(m, "slots").iter().map(|v| {
                structure([
                    q(v, "id"),
                    q(v, "type_id"),
                    q(v, "scope"),
                    q(v, "lifecycle_policy_id"),
                ])
            })),
            list(array(m, "targets").iter().map(|t| {
                structure([
                    q(t, "id"),
                    q(t, "role_id"),
                    q(t, "stage_id"),
                    q(t, "key_type_id"),
                    q(t, "peer_mode"),
                    q(t, "output_kind"),
                    strings(t, "property_definition_ids"),
                    q(t, "partnering_profile_id"),
                    q(t, "exposure_profile_id"),
                ])
            })),
        ])
    }
    fn model(&mut self, m: &Value, model: &Model) -> String {
        let registry = self.registry(m, model);
        let roles = list(array(m, "roles").iter().enumerate().map(|(ri, r)| {
            let blocks = list(array(r, "blocks").iter().enumerate().map(|(bi, b)| {
                let path = format!("/roles/{ri}/blocks/{bi}");
                self.name(&format!("{path}/id"), get(b, "id"));
                let steps = list(array(b, "steps").iter().enumerate().map(|(si, s)| {
                    let loc = format!("{path}/steps/{si}");
                    tuple([quote(&loc), self.step(s, &loc)])
                }));
                let endpath = format!("{path}/terminator");
                structure([
                    q(b, "id"),
                    steps,
                    quote(&endpath),
                    self.end(&b["terminator"], &endpath),
                ])
            }));
            structure([
                q(r, "id"),
                strings(r, "parameter_value_ids"),
                q(r, "entry_block"),
                blocks,
            ])
        }));
        let contexts = list(array(m, "contexts").iter().enumerate().map(|(i, c)| {
            structure([
                q(c, "id"),
                q(c, "role_id"),
                q(c, "stage_id"),
                q(c, "purpose"),
                self.term(&c["recipe"], &format!("/contexts/{i}/recipe")),
            ])
        }));
        let messages = list(array(m, "messages").iter().map(|v| {
            tuple([
                q(v, "id"),
                q(v, "constructor_id"),
                q(v, "sender_role"),
                q(v, "receiver_role"),
                q(v, "encoding_id"),
            ])
        }));
        let holes = list(array(m, "holes").iter().map(|v| {
            tuple([
                q(v, "id"),
                q(v, "object_path"),
                q(v, "expected_type_id"),
                q(v, "reason"),
                strings(v, "blocked_obligation_ids"),
            ])
        }));
        structure([
            q(&m["protocol"], "id"),
            registry,
            roles,
            contexts,
            messages,
            holes,
        ])
    }
}

pub fn operational_ast(m: &Value) -> Value {
    fn clean(v: &Value) -> Value {
        match v {
            Value::Array(xs) => Value::Array(xs.iter().map(clean).collect()),
            Value::Object(xs) if xs.get("kind").and_then(Value::as_str) == Some("literal") => {
                v.clone()
            }
            Value::Object(xs) => Value::Object(
                xs.iter()
                    .filter(|(k, _)| {
                        ![
                            "provenance",
                            "security_assumption_ids",
                            "cost_category",
                            "cost_evidence_refs",
                            "intended_visibility",
                            "assessment",
                            "source_ids",
                            "pinned_source_ids",
                            "case_kind",
                            "fragment_description",
                            "format_version",
                        ]
                        .contains(&k.as_str())
                    })
                    .map(|(k, v)| (k.clone(), clean(v)))
                    .collect(),
            ),
            _ => v.clone(),
        }
    }
    clean(m)
}

fn environment(p: &OperationalProfile) -> String {
    structure([
        quote(&p.interpretation),
        quote(&p.phase_policy),
        list(p.exposure_interfaces.iter().map(|s| quote(s))),
        list(p.parties.iter().map(|s| quote(s))),
        list(p.credentials.iter().map(|c| {
            structure([
                quote(&c.domain),
                quote(&c.reference),
                quote(&c.principal),
                quote(&c.key_owner),
            ])
        })),
        quote(&p.kem_correctness),
        list(p.correctness_error_sessions.iter().map(|s| quote(s))),
    ])
}

pub fn export(model_bytes: &[u8], profile_bytes: &[u8], output: &Path) -> Result<Value, String> {
    let model = crate::parse_model(model_bytes)?;
    crate::transport::unique(profile_bytes).map_err(|e| format!("profile: {e}"))?;
    let profile_value: Value =
        serde_json::from_slice(profile_bytes).map_err(|e| format!("profile: {e}"))?;
    let profile: OperationalProfile =
        serde_json::from_value(profile_value.clone()).map_err(|e| {
            format!("profile: {e}; only schema 1.0 restricted_symbolic_v1 is supported")
        })?;
    profile.validate()?;

    for (i, encoding) in model.encodings.iter().enumerate() {
        let mut isolated = model.clone();
        isolated.primitives.clear();
        isolated.encodings = vec![encoding.clone()];
        contracts::contracts(&isolated).map_err(|e| format!("model#/encodings/{i}: {e}"))?;
    }
    for (i, p) in model.primitives.iter().enumerate() {
        contracts::operation(p).map_err(|e| format!("model#/primitives/{i}/law_ids: {e}"))?;
        let mut isolated = model.clone();
        isolated.primitives = vec![p.clone()];
        contracts::contracts(&isolated).map_err(|e| format!("model#/primitives/{i}: {e}"))?;
    }
    let kernel = check::check(&model).map_err(|e| {

        let mut pointer = String::new();
        for (ri, role) in model.roles.iter().enumerate() {
            if let Some(rest) = e.strip_prefix(&format!("role {}: ", role.id)) {
                pointer = format!("/roles/{ri}");
                for (bi, block) in role.blocks.iter().enumerate() {
                    if rest.starts_with(&format!("block {}: ", block.id)) {
                        pointer = format!("/roles/{ri}/blocks/{bi}");
                        break;
                    }
                }
                break;
            }
        }
        format!("model#{pointer}: kernel rejection: {e}")
    })?;
    contracts::contracts(&model).map_err(|e| format!("model#/encodings: {e}"))?;
    let m = serde_json::to_value(&model).map_err(|e| e.to_string())?;
    let mut emitter = Emitter::default();
    let program = emitter.model(&m, &model);
    let model_hash = raw_digest(model_bytes);
    let profile_hash = raw_digest(profile_bytes);
    let identity = raw_digest(format!("{model_hash}:{profile_hash}").as_bytes());
    let module = format!("VAKE.Generated.M{identity}");
    let ns = format!("VAKE.Generated.M{identity}");
    let export_version = VERSION;
    let content = format!(
        "import VAKE.Target.Global\nset_option maxRecDepth 100000\nnamespace {ns}\nopen VAKE\ndef modelRawSha256 : String := {}\ndef profileRawSha256 : String := {}\ndef program : Target.Program :=\n{program}\ndef environment : Environment :=\n{}\nend {ns}\n",
        quote(&model_hash),
        quote(&profile_hash),
        environment(&profile)
    );
    let module_path = format!("VAKE/Generated/M{identity}.lean");
    let mut files = vec![
        (module_path.clone(), content.into_bytes()),
        ("model.json".into(), model_bytes.to_vec()),
        ("operational-profile.json".into(), profile_bytes.to_vec()),
    ];
    for (name, value) in [
        (
            "source-map.json",
            json!({"schema_version":"1.0","locations":emitter.locations,"symbols":emitter.symbols}),
        ),
        ("operational-ast.json", operational_ast(&m)),
    ] {
        files.push((
            name.into(),
            (serde_json::to_string_pretty(&value).map_err(|e| e.to_string())? + "\n").into_bytes(),
        ));
    }
    let contracts = json!({
        "profile_source_raw_sha256":raw_digest(include_bytes!("profile.rs")),
        "contract_admission_raw_sha256":raw_digest(include_bytes!("contracts.rs")),
        "kernel_source_raw_sha256":raw_digest(include_bytes!("check.rs")),
        "typed_ast_source_raw_sha256":raw_digest(include_bytes!("ir.rs")),
        "transport_source_raw_sha256":raw_digest(include_bytes!("transport.rs")),
        "metadata_adapter_raw_sha256":raw_digest(include_bytes!("admission.rs"))
    });
    let manifest = json!({"schema_version":"1.0","evidence_kind":"lean_export","exporter_version":export_version,
        "exporter_source_raw_sha256":raw_digest(include_bytes!("lean_export.rs")),"model_raw_sha256":model_hash,"profile_raw_sha256":profile_hash,
        "model_canonical_fingerprint":crate::profile::fingerprint(&model),"profile_canonical_fingerprint":crate::profile::fingerprint(&profile_value),
        "operational_ast_fingerprint":crate::profile::fingerprint(&operational_ast(&m)),"contracts":contracts,
        "toolchain":TOOLCHAIN,"scope":"restricted_symbolic_v1 syntax; separate original-JSON import and Lean proof verification required",
        "closure":if kernel.closed {"closed"}else{"open"},"holes":kernel.holes,"module":module,
        "theorem_module":format!("VAKE.Generated.B{identity}"),
        "theorem_names":["binding","profile_binding","step_preservation","trace_preservation","trace_reflection"],
        "theorem_status":"not_checked_by_export_command","security_properties":"open",
        "assumptions":["JSON parsing and independent importer trust","formal source semantics source-review boundary","explicit symbolic and network contracts","Lean kernel"],
        "files":files.iter().map(|(path,bytes)|json!({"path":path,"bytes":bytes.len(),"raw_sha256":raw_digest(bytes)})).collect::<Vec<_>>()});

    if output.exists()
        && fs::read_dir(output)
            .map_err(|e| e.to_string())?
            .next()
            .is_some()
    {
        return Err("output directory must be absent or empty".into());
    }
    for (path, bytes) in files {
        let dest = output.join(path);
        fs::create_dir_all(dest.parent().expect("parent")).map_err(|e| e.to_string())?;
        fs::write(dest, bytes).map_err(|e| e.to_string())?;
    }
    fs::write(
        output.join("export-manifest.json"),
        serde_json::to_string_pretty(&manifest).map_err(|e| e.to_string())? + "\n",
    )
    .map_err(|e| e.to_string())?;
    Ok(manifest)
}
