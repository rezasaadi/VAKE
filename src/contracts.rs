use crate::ir::{Model, Primitive};
use std::collections::BTreeSet;

pub fn operation(p: &Primitive) -> Result<String, String> {
    let ops: Vec<_> = p.law_ids.iter().filter(|x| x.starts_with("Op.")).collect();
    if ops.len() == 1 && p.law_ids.len() == 1 {
        return Ok(ops[0][3..].into());
    }
    if ops.is_empty() && p.law_ids == ["FreshPerSession"] {
        return Ok("fresh".into());
    }
    if ops.is_empty() && p.law_ids == ["HashOperationalFunction"] {
        return Ok("hash".into());
    }
    Err(format!(
        "unsupported contract {}: exactly one Op.* operational law required",
        p.id
    ))
}

pub fn contracts(model: &Model) -> Result<(), String> {
    for p in &model.primitives {
        let op = operation(p)?;
        if op.starts_with("edhoc_") || op.starts_with("tls_") || op == "validate_kem_credential" {
            return Err(format!(
                "unsupported standalone operation {op}: P2/P3 profiles are excluded"
            ));
        }
        let ins: Vec<_> = p.inputs.iter().map(|x| x.type_id.as_str()).collect();
        let success = p
            .outcomes
            .iter()
            .find(|o| o.tag == "ok")
            .ok_or_else(|| format!("{} missing ok outcome", p.id))?;
        let outs: Vec<_> = success
            .payload
            .iter()
            .map(|x| (x.name.as_str(), x.type_id.as_str()))
            .collect();
        let types: Vec<_> = outs.iter().map(|(_, t)| *t).collect();
        let (family, mode, expected_in, expected_out, may_fail): (
            &str,
            &str,
            Vec<&str>,
            Vec<&str>,
            bool,
        ) = match op.as_str() {
            "fresh" => ("generator", "effectful_total", vec![], vec!["Nonce"], false),
            "hash" => (
                "hash",
                "pure_total",
                vec!["Bytes"],
                vec!["HashDigest"],
                false,
            ),
            "extract" => (
                "KDF",
                "pure_total",
                vec!["Bytes", "SharedSecret"],
                vec!["Prk"],
                false,
            ),
            "expand" => (
                "KDF",
                "pure_total",
                vec!["Prk", "Label", "HashDigest", "Nat"],
                types.clone(),
                false,
            ),
            "bytes_view" => ("codec", "pure_total", ins.clone(), vec!["Bytes"], false),
            "sign" => (
                "signature",
                "pure_total",
                vec!["SignatureSecretKey", "Bytes"],
                vec!["Signature"],
                false,
            ),
            "verify" => (
                "signature",
                "effectful_result",
                vec!["SignaturePublicKey", "Bytes", "Signature"],
                vec![],
                true,
            ),
            "kem_keygen" => (
                "KEM",
                "effectful_total",
                vec![],
                vec!["KemPublicKey", "KemSecretKey"],
                false,
            ),
            "kem_encap" => (
                "KEM",
                "effectful_total",
                vec!["KemPublicKey"],
                vec!["KemCiphertext", "SharedSecret"],
                false,
            ),
            "kem_decap" => (
                "KEM",
                if p.failure_profile == "explicit_error" {
                    "effectful_result"
                } else {
                    "effectful_total"
                },
                vec!["KemSecretKey", "KemCiphertext"],
                vec!["SharedSecret"],
                p.failure_profile == "explicit_error",
            ),
            "decode" => (
                "codec",
                "effectful_result",
                vec!["Bytes"],
                types.clone(),
                true,
            ),
            "credential" => (
                "credential",
                "effectful_result",
                vec!["Label", "CredentialId", "Principal"],
                vec!["SignaturePublicKey"],
                true,
            ),
            "credential_resolve" => (
                "credential",
                "effectful_result",
                vec!["Label", "CredentialId", "Nat"],
                vec!["Credential"],
                true,
            ),
            "validate_credential" => (
                "credential",
                "effectful_result",
                vec!["Credential", "Label", "Principal"],
                vec!["SignaturePublicKey"],
                true,
            ),
            "eq" => (
                "public_check",
                "pure_total",
                ins.clone(),
                vec!["Bool"],
                false,
            ),
            "and" => (
                "public_check",
                "pure_total",
                vec!["Bool", "Bool"],
                vec!["Bool"],
                false,
            ),
            "mac" => (
                "MAC",
                "pure_total",
                vec!["MacKey", "Bytes"],
                vec!["MacTag"],
                false,
            ),
            "check_mac" => (
                "MAC",
                "effectful_result",
                vec!["MacKey", "Bytes", "MacTag"],
                vec![],
                true,
            ),
            "dh_keygen" => (
                "DH",
                "effectful_total",
                vec![],
                vec!["DhPublic", "DhSecret"],
                false,
            ),
            "dh_validate" => (
                "DH",
                "effectful_result",
                vec!["DhPublic"],
                vec!["DhPublic"],
                true,
            ),
            "dh_shared" => (
                "DH",
                "effectful_result",
                vec!["DhSecret", "DhPublic"],
                vec!["SharedSecret"],
                true,
            ),
            "aead_seal" => (
                "AEAD",
                "pure_total",
                vec!["AeadKey", "AeadNonce", "Bytes", "Bytes"],
                vec!["AeadCiphertext"],
                false,
            ),
            "aead_open" => (
                "AEAD",
                "effectful_result",
                vec!["AeadKey", "AeadNonce", "AeadCiphertext", "Bytes"],
                vec!["Bytes"],
                true,
            ),
            "xor" => (
                "xor",
                "pure_total",
                vec!["Bytes", "Bytes"],
                vec!["Bytes"],
                false,
            ),
            _ => return Err(format!("unsupported primitive operation {op}")),
        };
        if ins != expected_in || types != expected_out || p.family != family || p.mode != mode {
            return Err(format!(
                "backend signature/mode/family mismatch for {} ({op})",
                p.id
            ));
        }
        if op == "eq" && (ins.len() != 2 || ins[0] != ins[1]) {
            return Err("eq needs two identical types".into());
        }
        if op == "bytes_view"
            && (ins.len() != 1
                || !["Prk", "SharedSecret", "HashDigest", "MacTag", "Nonce"].contains(&ins[0]))
        {
            return Err("unsupported semantic byte view".into());
        }
        if op == "expand"
            && (types.len() != 1
                || !["MacKey", "SessionKey", "AeadKey", "Prk", "Bytes"].contains(&types[0]))
        {
            return Err("unsupported expand output".into());
        }
        if op == "decode"
            && (types.len() != 1
                || model.ty(types[0])?.kind != "record"
                || model
                    .constructors
                    .iter()
                    .filter(|c| c.type_id == types[0])
                    .count()
                    != 1)
        {
            return Err("decode requires one unambiguous record constructor".into());
        }
        if op == "decode"
            && model
                .encodings
                .iter()
                .filter(|e| e.input_type_ids.iter().any(|t| t == types[0]))
                .count()
                != 1
        {
            return Err("decode requires one unambiguous encoding per result record type".into());
        }
        let failure = if op == "credential_resolve" {
            "not_found"
        } else {
            "invalid"
        };
        let tags: BTreeSet<_> = p.outcomes.iter().map(|o| o.tag.as_str()).collect();
        if tags
            != if may_fail {
                BTreeSet::from(["ok", failure])
            } else {
                BTreeSet::from(["ok"])
            }
        {
            return Err(format!("unsupported outcome tags for {}", p.id));
        }
        if p.outcomes
            .iter()
            .filter(|o| o.tag != "ok")
            .any(|o| !o.payload.is_empty())
        {
            return Err("failure payload must be empty".into());
        }
        if op == "kem_decap" {
            if !["implicit_rejection", "explicit_error"].contains(&p.failure_profile.as_str()) {
                return Err("KEM decapsulation must declare rejection profile".into());
            }
        } else if p.failure_profile != if may_fail { "explicit_error" } else { "none" } {
            return Err(format!("unsupported failure profile for {}", p.id));
        }

        for (i, input) in p.inputs.iter().enumerate() {
            let secret = matches!(op.as_str(),"extract" if i==1)
                || matches!(op.as_str(),"bytes_view" if i==0)
                || matches!(op.as_str(),"expand"|"sign"|"mac"|"check_mac"|"kem_decap"|"dh_shared"|"aead_seal"|"aead_open" if i==0);
            if input.position_kind != if secret { "secret" } else { "public" } {
                return Err(format!(
                    "argument-position contract mismatch for {} input {}",
                    p.id, i
                ));
            }
        }
    }
    for e in &model.encodings {
        if e.family != "fixture_tlv" {
            return Err(format!(
                "unsupported standalone codec {}: only fixture_tlv is admitted",
                e.family
            ));
        }
        let prefix = "FixtureEncoding";
        let inverse = format!("{prefix}Inverse");
        let injective = format!("{prefix}Injective");
        if !e.contract_ids.contains(&inverse)
            || e.contract_ids
                .iter()
                .any(|c| c != &inverse && c != &injective)
        {
            return Err(format!("unresolved codec contracts for {}", e.id));
        }
    }
    Ok(())
}
