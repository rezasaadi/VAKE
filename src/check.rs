use crate::ir::*;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize)]
pub struct CheckReport {
    pub closed: bool,
    pub holes: Vec<String>,
    pub roles: usize,
    pub blocks: usize,
    pub values: usize,
}

fn ensure(ok: bool, message: impl Into<String>) -> Result<(), String> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn id(s: &str) -> Result<(), String> {
    ensure(
        s.as_bytes().first().is_some_and(u8::is_ascii_alphabetic)
            && s.bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"_.:/-".contains(&c)),
        format!("invalid identifier: {s:?}"),
    )
}
fn nonempty(s: &str, context: &str) -> Result<(), String> {
    ensure(!s.is_empty(), format!("empty {context}"))
}
fn choice(s: &str, options: &[&str], context: &str) -> Result<(), String> {
    ensure(options.contains(&s), format!("invalid {context}: {s}"))
}
fn unique<'a>(items: impl IntoIterator<Item = &'a str>, context: &str) -> Result<(), String> {
    let mut seen = BTreeSet::new();
    for item in items {
        id(item)?;
        ensure(seen.insert(item), format!("duplicate {context}: {item}"))?;
    }
    Ok(())
}
fn ids(items: &[String]) -> Result<(), String> {
    for item in items {
        id(item)?;
    }
    Ok(())
}
fn source(m: &Model, s: &SourceRef) -> Result<(), String> {
    id(&s.source_id)?;
    ensure(
        m.source_ids.contains(&s.source_id),
        format!("unregistered source {}", s.source_id),
    )?;
    nonempty(&s.locator, "source locator")
}
fn provenance(m: &Model, p: &Provenance) -> Result<(), String> {
    choice(
        &p.kind,
        &[
            "specified",
            "constructed",
            "modeling_choice",
            "assumption",
            "unresolved",
        ],
        "provenance kind",
    )?;
    nonempty(&p.rationale, "provenance rationale")?;
    for s in &p.source_refs {
        source(m, s)?;
    }
    Ok(())
}
fn fields(m: &Model, fields: &[Field]) -> Result<(), String> {
    unique(fields.iter().map(|f| f.name.as_str()), "field")?;
    for f in fields {
        m.ty(&f.type_id)?;
    }
    Ok(())
}

pub fn check(m: &Model) -> Result<CheckReport, String> {
    ensure(m.format_version == "0.1", "unsupported format_version")?;
    id(&m.protocol.id)?;
    choice(
        &m.protocol.case_kind,
        &[
            "constructed_fixture",
            "published_fragment",
            "syntax_example",
        ],
        "case kind",
    )?;
    nonempty(&m.protocol.fragment_description, "fragment description")?;
    unique(m.source_ids.iter().map(String::as_str), "source id")?;
    unique(
        m.protocol.pinned_source_ids.iter().map(String::as_str),
        "pinned source id",
    )?;
    for src in &m.protocol.pinned_source_ids {
        ensure(
            m.source_ids.contains(src),
            format!("unknown pinned source: {src}"),
        )?;
    }
    provenance(m, &m.protocol.provenance)?;
    id(&m.assessment.case_profile_id)?;
    id(&m.assessment.obligation_ledger_id)?;
    macro_rules! registry {
        ($($field:ident),*) => { $(unique(m.$field.iter().map(|x| x.id.as_str()), stringify!($field))?;)* };
    }
    registry!(
        types,
        primitives,
        constructors,
        encodings,
        values,
        slots,
        messages,
        contexts,
        roles,
        targets,
        holes
    );
    for t in &m.types {
        choice(
            &t.kind,
            &["base", "semantic", "record", "result"],
            "type kind",
        )?;
        ids(&t.parameters)?;
        fields(m, &t.fields)?;
        provenance(m, &t.provenance)?;
        if [
            "Bytes",
            "Bool",
            "Nat",
            "Principal",
            "RoleId",
            "SessionId",
            "SuiteId",
            "CredentialId",
            "Label",
        ]
        .contains(&t.id.as_str())
        {
            ensure(
                t.kind == "base",
                format!("reserved base sort {} has wrong kind", t.id),
            )?;
        }
        if [
            "Nonce",
            "HashDigest",
            "SignaturePublicKey",
            "SignatureSecretKey",
            "Signature",
            "KemPublicKey",
            "KemSecretKey",
            "KemCiphertext",
            "SharedSecret",
            "DhPublic",
            "DhSecret",
            "Prk",
            "MacKey",
            "MacTag",
            "AeadKey",
            "AeadNonce",
            "AeadCiphertext",
            "SessionKey",
            "Credential",
            "KemCredential",
        ]
        .contains(&t.id.as_str())
        {
            ensure(
                t.kind == "semantic",
                format!("reserved semantic sort {} has wrong kind", t.id),
            )?;
        }
        if t.kind == "record" {
            ensure(
                t.primitive_ref.is_none(),
                format!("record {} cannot refer to a primitive", t.id),
            )?;
        } else {
            ensure(
                t.fields.is_empty(),
                format!("non-record {} has fields", t.id),
            )?;
        }
        if t.kind == "base" {
            choice(
                &t.id,
                &[
                    "Bytes",
                    "Bool",
                    "Nat",
                    "Principal",
                    "RoleId",
                    "SessionId",
                    "SuiteId",
                    "CredentialId",
                    "Label",
                ],
                "base type",
            )?;
            ensure(
                t.parameters.is_empty(),
                format!("base {} has unsupported refinements", t.id),
            )?;
        }
        if t.kind == "result" {
            let p = m.primitive(
                t.primitive_ref
                    .as_deref()
                    .ok_or_else(|| format!("result {} has no primitive_ref", t.id))?,
            )?;
            ensure(
                p.mode != "pure_total",
                format!("result {} refers to pure primitive", t.id),
            )?;
        } else {
            ensure(
                t.primitive_ref.is_none(),
                format!("non-result {} has primitive_ref", t.id),
            )?;
        }
    }

    let mut visiting = BTreeSet::new();
    let mut finished = BTreeSet::new();
    for t in &m.types {
        type_acyclic(m, &t.id, &mut visiting, &mut finished)?;
    }
    for p in &m.primitives {
        choice(
            &p.family,
            &[
                "KEM",
                "signature",
                "DH",
                "hash",
                "KDF",
                "MAC",
                "AEAD",
                "xor",
                "codec",
                "credential",
                "generator",
                "public_check",
            ],
            "primitive family",
        )?;
        choice(
            &p.mode,
            &["pure_total", "effectful_total", "effectful_result"],
            "primitive mode",
        )?;
        choice(
            &p.failure_profile,
            &[
                "none",
                "explicit_error",
                "implicit_rejection",
                "case_defined",
            ],
            "failure profile",
        )?;
        choice(
            &p.cost_category,
            &["low", "expensive_pq", "other", "unknown"],
            "cost category",
        )?;
        provenance(m, &p.provenance)?;
        ids(&p.law_ids)?;
        ids(&p.security_assumption_ids)?;
        for s in &p.cost_evidence_refs {
            source(m, s)?;
        }
        unique(p.inputs.iter().map(|i| i.name.as_str()), "primitive input")?;
        for input in &p.inputs {
            m.ty(&input.type_id)?;
            choice(
                &input.position_kind,
                &["public", "secret", "randomness"],
                "input position",
            )?;
        }
        unique(p.outcomes.iter().map(|o| o.tag.as_str()), "outcome tag")?;
        ensure(
            !p.outcomes.is_empty(),
            format!("primitive {} has no outcomes", p.id),
        )?;
        for o in &p.outcomes {
            fields(m, &o.payload)?;
        }
        if p.mode == "pure_total" {
            ensure(
                p.failure_profile == "none"
                    && p.outcomes.len() == 1
                    && p.outcomes[0].payload.len() == 1
                    && p.inputs.iter().all(|i| i.position_kind != "randomness"),
                format!(
                    "pure primitive {} must be deterministic, total and single-output",
                    p.id
                ),
            )?;
        }
        if p.mode == "effectful_total" {
            ensure(
                p.outcomes.len() == 1
                    && matches!(p.failure_profile.as_str(), "none" | "implicit_rejection"),
                format!("effectful_total {} cannot expose failure outcomes", p.id),
            )?;
        }
        if p.failure_profile == "implicit_rejection" {
            ensure(
                p.outcomes.len() == 1,
                format!(
                    "implicit rejection {} cannot expose validity outcomes",
                    p.id
                ),
            )?;
        }
    }
    for c in &m.constructors {
        let t = m.ty(&c.type_id)?;
        ensure(
            t.kind == "record" && c.fields == t.fields,
            format!(
                "constructor {} layout differs from record type {}",
                c.id, t.id
            ),
        )?;
        fields(m, &c.fields)?;
        provenance(m, &c.provenance)?;
    }
    for e in &m.encodings {
        choice(
            &e.family,
            &[
                "fixture_tlv",
                "tls_abstract",
                "cbor_abstract",
                "cose_abstract",
                "edhoc_sequence",
                "edhoc_array",
                "case_defined",
            ],
            "encoding family",
        )?;
        unique(
            e.input_type_ids.iter().map(String::as_str),
            "encoding input type",
        )?;
        for t in &e.input_type_ids {
            ensure(
                m.ty(t)?.kind == "record",
                format!("encoding {} input {t} is not record", e.id),
            )?;
        }
        ids(&e.contract_ids)?;
        provenance(m, &e.provenance)?;
    }
    for v in &m.values {
        m.ty(&v.type_id)?;
        m.role(&v.owner_role)?;
        choice(&v.storage_kind, &["parameter", "local"], "storage kind")?;
        choice(
            &v.intended_visibility,
            &["public", "secret", "unspecified"],
            "intended visibility",
        )?;
        ensure(
            !m.slots.iter().any(|s| s.id == v.id),
            format!("ambiguous value/slot id {}", v.id),
        )?;
        provenance(m, &v.provenance)?;
    }
    for s in &m.slots {
        m.ty(&s.type_id)?;
        choice(&s.scope, &["session", "party_persistent"], "slot scope")?;
        id(&s.lifecycle_policy_id)?;
        provenance(m, &s.provenance)?;
    }
    for msg in &m.messages {
        let c = m.constructor(&msg.constructor_id)?;
        let e = m.encoding(&msg.encoding_id)?;
        ensure(
            e.input_type_ids.contains(&c.type_id),
            format!("message {} encoder rejects constructor type", msg.id),
        )?;
        m.role(&msg.sender_role)?;
        m.role(&msg.receiver_role)?;
        provenance(m, &msg.provenance)?;
    }
    for t in &m.targets {
        m.role(&t.role_id)?;
        m.ty(&t.key_type_id)?;
        id(&t.stage_id)?;
        choice(&t.peer_mode, &["named", "anonymous", "none"], "peer mode")?;
        choice(
            &t.output_kind,
            &["internal_stage", "application_key", "output_secret"],
            "output kind",
        )?;
        ids(&t.property_definition_ids)?;
        id(&t.partnering_profile_id)?;
        id(&t.exposure_profile_id)?;
        provenance(m, &t.provenance)?;
    }
    for h in &m.holes {
        m.ty(&h.expected_type_id)?;
        nonempty(&h.object_path, "hole object_path")?;
        nonempty(&h.reason, "hole reason")?;
        ids(&h.blocked_obligation_ids)?;
        provenance(m, &h.provenance)?;
    }
    for r in &m.roles {
        check_role(m, r).map_err(|e| format!("role {}: {e}", r.id))?;
    }
    for c in &m.contexts {
        m.role(&c.role_id)?;
        id(&c.stage_id)?;
        nonempty(&c.purpose, "context purpose")?;
        provenance(m, &c.provenance)?;

        let declared = m
            .values
            .iter()
            .filter(|v| v.owner_role == c.role_id)
            .map(|v| v.id.clone())
            .collect();
        term_type(m, &c.role_id, &declared, &c.recipe)?;
    }
    Ok(CheckReport {
        closed: m.holes.is_empty(),
        holes: m.holes.iter().map(|h| h.id.clone()).collect(),
        roles: m.roles.len(),
        blocks: m.roles.iter().map(|r| r.blocks.len()).sum(),
        values: m.values.len(),
    })
}

fn type_acyclic(
    m: &Model,
    id: &str,
    visiting: &mut BTreeSet<String>,
    finished: &mut BTreeSet<String>,
) -> Result<(), String> {
    if finished.contains(id) {
        return Ok(());
    }
    ensure(
        visiting.insert(id.to_string()),
        format!("recursive type: {id}"),
    )?;
    let t = m.ty(id)?;
    for f in &t.fields {
        type_acyclic(m, &f.type_id, visiting, finished)?;
    }
    if let Some(p) = &t.primitive_ref {
        for o in &m.primitive(p)?.outcomes {
            for f in &o.payload {
                type_acyclic(m, &f.type_id, visiting, finished)?;
            }
        }
    }
    visiting.remove(id);
    finished.insert(id.to_string());
    Ok(())
}

type Available = BTreeSet<String>;
fn owned<'a>(m: &'a Model, role: &str, value: &str) -> Result<&'a ValueDecl, String> {
    let v = m.value(value)?;
    ensure(
        v.owner_role == role,
        format!("cross-role reference {value} belongs to {}", v.owner_role),
    )?;
    Ok(v)
}
fn available<'a>(
    m: &'a Model,
    role: &str,
    env: &Available,
    value: &str,
) -> Result<&'a ValueDecl, String> {
    let v = owned(m, role, value)?;
    ensure(
        env.contains(value),
        format!("value {value} has no dominating live definition"),
    )?;
    Ok(v)
}
fn same(got: &str, expected: &str) -> Result<(), String> {
    ensure(
        got == expected,
        format!("type mismatch: expected {expected}, got {got}"),
    )
}

pub fn term_type(
    m: &Model,
    role: &str,
    env: &BTreeSet<String>,
    term: &Term,
) -> Result<String, String> {
    match term {
        Term::Ref { value_id } => Ok(available(m, role, env, value_id)?.type_id.clone()),
        Term::Literal { type_id, value } => {
            let t = m.ty(type_id)?;
            ensure(
                t.kind == "base",
                format!("literal cannot fabricate non-base type {type_id}"),
            )?;
            let ok = match type_id.as_str() {
                "Bool" => value.is_boolean(),
                "Nat" => value.as_u64().is_some(),
                "Bytes" | "Principal" | "RoleId" | "SessionId" | "SuiteId" | "CredentialId"
                | "Label" => value.is_string(),
                _ => false,
            };
            ensure(ok, format!("literal does not match base sort {type_id}"))?;
            Ok(type_id.clone())
        }
        Term::Record {
            constructor_id,
            fields,
        } => {
            let c = m.constructor(constructor_id)?;
            ensure(
                fields.len() == c.fields.len(),
                format!("record {constructor_id} field count mismatch"),
            )?;
            for (actual, expected) in fields.iter().zip(&c.fields) {
                ensure(
                    actual.name == expected.name,
                    format!("record {constructor_id} field order/name mismatch"),
                )?;
                same(&term_type(m, role, env, &actual.term)?, &expected.type_id)?;
            }
            Ok(c.type_id.clone())
        }
        Term::Project { record, field } => {
            let ty = term_type(m, role, env, record)?;
            let t = m.ty(&ty)?;
            ensure(
                t.kind == "record",
                format!("projection from non-record {ty}"),
            )?;
            t.fields
                .iter()
                .find(|f| &f.name == field)
                .map(|f| f.type_id.clone())
                .ok_or_else(|| format!("record {ty} has no field {field}"))
        }
        Term::Encode {
            encoding_id,
            record,
        } => {
            let ty = term_type(m, role, env, record)?;
            let e = m.encoding(encoding_id)?;
            ensure(
                e.input_type_ids.contains(&ty),
                format!("encoding {encoding_id} rejects type {ty}"),
            )?;
            ensure(m.ty("Bytes")?.kind == "base", "Bytes must be a base sort")?;
            Ok("Bytes".into())
        }
        Term::Apply { primitive_id, args } => {
            let p = m.primitive(primitive_id)?;
            ensure(
                p.mode == "pure_total",
                format!("Apply cannot conceal effectful primitive {primitive_id}"),
            )?;
            check_args(m, role, env, p, args)?;
            p.outcomes
                .first()
                .and_then(|o| o.payload.first())
                .map(|f| f.type_id.clone())
                .ok_or_else(|| format!("pure primitive {primitive_id} has no output"))
        }
        Term::Hole { hole_id, type_id } => {
            let h = m.hole(hole_id)?;
            same(type_id, &h.expected_type_id)?;
            m.ty(type_id)?;
            Ok(type_id.clone())
        }
    }
}

fn check_args(
    m: &Model,
    role: &str,
    env: &Available,
    p: &Primitive,
    args: &[Term],
) -> Result<(), String> {
    ensure(
        args.len() == p.inputs.len(),
        format!("primitive {} argument count mismatch", p.id),
    )?;
    for (arg, input) in args.iter().zip(&p.inputs) {
        same(&term_type(m, role, env, arg)?, &input.type_id)?;
    }
    Ok(())
}
fn define(m: &Model, role: &str, env: &mut Available, value: &str, ty: &str) -> Result<(), String> {
    let v = owned(m, role, value)?;
    ensure(
        v.storage_kind == "local",
        format!("cannot redefine parameter {value}"),
    )?;
    same(ty, &v.type_id)?;
    ensure(
        env.insert(value.to_string()),
        format!("value {value} assigned twice"),
    )
}
fn target<'a>(m: &'a Model, role: &str, target: &str) -> Result<&'a Target, String> {
    let t = m.target(target)?;
    ensure(
        t.role_id == role,
        format!("target {target} belongs to role {}", t.role_id),
    )?;
    Ok(t)
}

fn check_role(m: &Model, r: &Role) -> Result<(), String> {
    provenance(m, &r.provenance)?;
    unique(
        r.parameter_value_ids.iter().map(String::as_str),
        "role parameter",
    )?;
    unique(r.blocks.iter().map(|b| b.id.as_str()), "block")?;
    r.block(&r.entry_block)?;
    let parameters: Available = r.parameter_value_ids.iter().cloned().collect();
    for param in &r.parameter_value_ids {
        ensure(
            owned(m, &r.id, param)?.storage_kind == "parameter",
            format!("{param} is not a parameter"),
        )?;
    }
    for v in m
        .values
        .iter()
        .filter(|v| v.owner_role == r.id && v.storage_kind == "parameter")
    {
        ensure(
            parameters.contains(&v.id),
            format!("parameter {} is not bound by its role", v.id),
        )?;
    }
    let mut defined = BTreeSet::new();
    let mut indegree: BTreeMap<String, usize> =
        r.blocks.iter().map(|b| (b.id.clone(), 0)).collect();
    for block in &r.blocks {
        provenance(m, &block.provenance)?;
        for step in &block.steps {
            provenance(m, step.provenance())?;
            if let Some(value) = step.defined_value() {
                declare_definition(m, r, value, &mut defined)?;
            }
        }
        if let Terminator::Match { arms, .. } = &block.terminator {
            unique(arms.iter().map(|a| a.tag.as_str()), "match arm")?;
            for arm in arms {
                unique(
                    arm.bindings.iter().map(|b| b.payload_name.as_str()),
                    "arm payload binding",
                )?;
                for b in &arm.bindings {
                    declare_definition(m, r, &b.value_id, &mut defined)?;
                }
            }
        }
        for successor in block.terminator.successors() {
            r.block(successor)?;
            *indegree.get_mut(successor).unwrap() += 1;
        }
    }
    for v in m
        .values
        .iter()
        .filter(|v| v.owner_role == r.id && v.storage_kind == "local")
    {
        ensure(
            defined.contains(&v.id),
            format!("local {} has no defining instruction or arm", v.id),
        )?;
    }
    ensure(
        indegree[&r.entry_block] == 0,
        "entry block has an incoming edge",
    )?;
    let mut queue: Vec<String> = indegree
        .iter()
        .filter(|(_, n)| **n == 0)
        .map(|(id, _)| id.clone())
        .collect();
    let mut incoming: BTreeMap<String, Vec<Available>> = BTreeMap::new();
    let mut processed = 0;
    while let Some(block_id) = queue.pop() {
        processed += 1;
        let block = r.block(&block_id)?;
        let mut env = match incoming.remove(&block_id) {
            Some(paths) => {
                let mut iter = paths.into_iter();
                let mut intersection = iter.next().unwrap_or_else(|| parameters.clone());
                for path in iter {
                    intersection.retain(|v| path.contains(v));
                }
                intersection
            }
            None => parameters.clone(),
        };
        for step in &block.steps {
            check_step(m, r, &mut env, step).map_err(|e| format!("block {block_id}: {e}"))?;
        }
        let edges = check_terminator(m, r, &env, &block.terminator)?;
        for (successor, edge_env) in edges {
            incoming
                .entry(successor.clone())
                .or_default()
                .push(edge_env);
            let count = indegree.get_mut(&successor).unwrap();
            *count -= 1;
            if *count == 0 {
                queue.push(successor);
            }
        }
    }
    ensure(processed == r.blocks.len(), "cycle in role control graph")
}

fn declare_definition(
    m: &Model,
    r: &Role,
    value: &str,
    defined: &mut Available,
) -> Result<(), String> {
    let v = owned(m, &r.id, value)?;
    ensure(
        v.storage_kind == "local",
        format!("attempt to define parameter {value}"),
    )?;
    ensure(
        defined.insert(value.to_string()),
        format!("local {value} has multiple definitions (including after erasure)"),
    )
}

fn check_step(m: &Model, r: &Role, env: &mut Available, s: &Step) -> Result<(), String> {
    let role = r.id.as_str();
    match s {
        Step::Assign {
            output_value_id,
            term,
            ..
        } => {
            let ty = term_type(m, role, env, term)?;
            define(m, role, env, output_value_id, &ty)?;
        }
        Step::Sample {
            output_value_id,
            generator_id,
            ..
        } => {
            let p = m.primitive(generator_id)?;
            ensure(
                p.family == "generator"
                    && p.mode == "effectful_total"
                    && p.inputs.is_empty()
                    && p.outcomes.len() == 1
                    && p.outcomes[0].payload.len() == 1,
                format!("Sample requires a nullary, single-output total generator: {generator_id}"),
            )?;
            define(
                m,
                role,
                env,
                output_value_id,
                &p.outcomes[0].payload[0].type_id,
            )?;
        }
        Step::Invoke {
            primitive_id,
            args,
            result_value_id,
            ..
        } => {
            let p = m.primitive(primitive_id)?;
            ensure(
                p.mode != "pure_total",
                format!("Invoke of pure primitive {primitive_id}; use Apply"),
            )?;
            check_args(m, role, env, p, args)?;
            let out = owned(m, role, result_value_id)?;
            let t = m.ty(&out.type_id)?;
            ensure(
                t.kind == "result" && t.primitive_ref.as_ref() == Some(primitive_id),
                format!("Invoke result {result_value_id} is not Result for {primitive_id}"),
            )?;
            define(m, role, env, result_value_id, &t.id)?;
        }
        Step::Receive {
            output_bytes_value_id,
            ..
        } => {
            ensure(m.ty("Bytes")?.kind == "base", "Receive requires base Bytes")?;
            define(m, role, env, output_bytes_value_id, "Bytes")?;
        }
        Step::Send {
            bytes, channel_id, ..
        } => {
            id(channel_id)?;
            same(&term_type(m, role, env, bytes)?, "Bytes")?;
        }
        Step::Read {
            slot_id,
            output_value_id,
            ..
        } => {
            define(m, role, env, output_value_id, &m.slot(slot_id)?.type_id)?;
        }
        Step::Write { slot_id, value, .. } => {
            same(&term_type(m, role, env, value)?, &m.slot(slot_id)?.type_id)?;
        }
        Step::Erase { object_id, .. } => {
            if m.slots.iter().any(|s| s.id == *object_id) {
                m.slot(object_id)?;
            } else {
                ensure(
                    owned(m, role, object_id)?.storage_kind == "local",
                    format!("cannot erase read-only parameter {object_id}"),
                )?;
                env.remove(object_id);
            }
        }
        Step::Emit {
            event_name,
            args,
            visibility,
            ..
        } => {
            id(event_name)?;
            choice(
                visibility,
                &["public", "local", "analysis"],
                "event visibility",
            )?;
            for arg in args {
                term_type(m, role, env, arg)?;
            }
        }
        Step::Accept {
            target_id,
            key,
            peer,
            ..
        } => {
            let declared = target(m, role, target_id)?;
            same(&term_type(m, role, env, key)?, &declared.key_type_id)?;
            ensure(
                peer.is_some() == (declared.peer_mode == "named"),
                format!(
                    "accept for target {target_id} must {} a peer for peer mode {}",
                    if declared.peer_mode == "named" { "name" } else { "not name" },
                    declared.peer_mode
                ),
            )?;
            if let Some(peer) = peer {
                same(&term_type(m, role, env, peer)?, "Principal")?;
            }
        }
        Step::Export { target_id, key, .. } => {
            same(
                &term_type(m, role, env, key)?,
                &target(m, role, target_id)?.key_type_id,
            )?;
        }
    }
    Ok(())
}

fn check_terminator(
    m: &Model,
    r: &Role,
    env: &Available,
    t: &Terminator,
) -> Result<Vec<(String, Available)>, String> {
    match t {
        Terminator::Jump { target_block } => Ok(vec![(target_block.clone(), env.clone())]),
        Terminator::Branch {
            condition,
            true_block,
            false_block,
        } => {
            same(&term_type(m, &r.id, env, condition)?, "Bool")?;
            Ok(vec![
                (true_block.clone(), env.clone()),
                (false_block.clone(), env.clone()),
            ])
        }
        Terminator::Match {
            result_value_id,
            arms,
        } => {
            let v = available(m, &r.id, env, result_value_id)?;
            let t = m.ty(&v.type_id)?;
            ensure(
                t.kind == "result",
                format!("Match on non-result {result_value_id}"),
            )?;
            let p = m.primitive(
                t.primitive_ref
                    .as_deref()
                    .ok_or("result primitive missing")?,
            )?;
            let mut edges = vec![];

            for arm in arms {
                let outcome = p
                    .outcomes
                    .iter()
                    .find(|o| o.tag == arm.tag)
                    .ok_or_else(|| format!("undeclared outcome {} for {}", arm.tag, p.id))?;
                let mut edge = env.clone();
                for bind in &arm.bindings {
                    let payload = outcome
                        .payload
                        .iter()
                        .find(|f| f.name == bind.payload_name)
                        .ok_or_else(|| {
                            format!("outcome {} has no payload {}", arm.tag, bind.payload_name)
                        })?;
                    define(m, &r.id, &mut edge, &bind.value_id, &payload.type_id)?;
                }
                edges.push((arm.target_block.clone(), edge));
            }
            Ok(edges)
        }
        Terminator::Stop { reason } => {
            nonempty(reason, "stop reason")?;
            Ok(vec![])
        }
        Terminator::Reject { target_ids, reason } => {
            nonempty(reason, "reject reason")?;
            unique(target_ids.iter().map(String::as_str), "rejected target")?;
            for id in target_ids {
                target(m, &r.id, id)?;
            }
            Ok(vec![])
        }
    }
}
