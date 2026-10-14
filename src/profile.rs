use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CredentialSpec {
    pub domain: String,
    pub reference: String,
    pub principal: String,
    pub key_owner: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OperationalProfile {
    pub schema_version: String,
    pub id: String,
    pub interpretation: String,
    pub phase_policy: String,
    pub exposure_interfaces: Vec<String>,
    pub parties: Vec<String>,
    pub credentials: Vec<CredentialSpec>,
    pub kem_correctness: String,
    pub correctness_error_sessions: Vec<String>,
}

impl OperationalProfile {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != "1.0" {
            return Err("profile#/schema_version: supported version is 1.0".into());
        }
        if self.interpretation != "restricted_symbolic_v1" {
            return Err("profile#/interpretation: unsupported operational interpretation".into());
        }
        if !["reject_unexpected_preserve_completed", "stuck_unexpected"]
            .contains(&self.phase_policy.as_str())
        {
            return Err("profile#/phase_policy: unsupported phase policy".into());
        }
        if !["ideal", "may_fail"].contains(&self.kem_correctness.as_str()) {
            return Err("profile#/kem_correctness: unsupported correctness selection".into());
        }
        if self.kem_correctness == "ideal" && !self.correctness_error_sessions.is_empty() {
            return Err("profile#/correctness_error_sessions: faults require may_fail".into());
        }
        for (i, interface) in self.exposure_interfaces.iter().enumerate() {
            if !["reveal_export", "reveal_state", "corrupt"].contains(&interface.as_str()) {
                return Err(format!(
                    "profile#/exposure_interfaces/{i}: unsupported exposure"
                ));
            }
        }
        let parties: BTreeSet<_> = self.parties.iter().collect();
        if parties.len() != self.parties.len() {
            return Err("profile#/parties: duplicate setup party".into());
        }
        for (i, cred) in self.credentials.iter().enumerate() {
            if !parties.contains(&cred.key_owner) {
                return Err(format!(
                    "profile#/credentials/{i}/key_owner: unknown setup party"
                ));
            }
        }
        Ok(())
    }
}

pub fn fingerprint<T: Serialize>(value: &T) -> String {

    let bytes = serde_json::to_vec(&serde_json::to_value(value).expect("serializable"))
        .expect("serializable");
    format!("{:x}", Sha256::digest(bytes))
}
