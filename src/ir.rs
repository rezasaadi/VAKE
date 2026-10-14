use serde::{Deserialize, Deserializer, Serialize};

fn required_option<'de, D, T>(d: D) -> Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::deserialize(d)
}

macro_rules! record {
    ($name:ident { $($field:ident: $ty:ty),* $(,)? }) => {
        #[derive(Clone, Debug, Serialize, Deserialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name { $(pub $field: $ty),* }
    };
}

record!(SourceRef {
    source_id: String,
    locator: String
});
record!(Provenance { kind: String, source_refs: Vec<SourceRef>, rationale: String });
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Field {
    pub name: String,
    pub type_id: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TypeDef {
    pub id: String,
    pub kind: String,
    pub parameters: Vec<String>,
    pub fields: Vec<Field>,
    #[serde(deserialize_with = "required_option")]
    pub primitive_ref: Option<String>,
    pub provenance: Provenance,
}
record!(Constructor { id: String, type_id: String, fields: Vec<Field>, provenance: Provenance });
record!(Encoding { id: String, input_type_ids: Vec<String>, family: String, contract_ids: Vec<String>, provenance: Provenance });
record!(ValueDecl {
    id: String,
    type_id: String,
    owner_role: String,
    storage_kind: String,
    intended_visibility: String,
    provenance: Provenance
});
record!(Input {
    name: String,
    type_id: String,
    position_kind: String
});
record!(Outcome { tag: String, payload: Vec<Field> });
record!(Primitive { id: String, family: String, mode: String, inputs: Vec<Input>, outcomes: Vec<Outcome>, failure_profile: String, law_ids: Vec<String>, security_assumption_ids: Vec<String>, cost_category: String, cost_evidence_refs: Vec<SourceRef>, provenance: Provenance });
record!(NamedTerm {
    name: String,
    term: Term
});

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Term {
    Ref {
        value_id: String,
    },
    Literal {
        type_id: String,
        value: serde_json::Value,
    },
    Record {
        constructor_id: String,
        fields: Vec<NamedTerm>,
    },
    Project {
        record: Box<Term>,
        field: String,
    },
    Encode {
        encoding_id: String,
        record: Box<Term>,
    },
    Apply {
        primitive_id: String,
        args: Vec<Term>,
    },
    Hole {
        hole_id: String,
        type_id: String,
    },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Step {
    Assign {
        output_value_id: String,
        term: Term,
        provenance: Provenance,
    },
    Sample {
        output_value_id: String,
        generator_id: String,
        provenance: Provenance,
    },
    Invoke {
        primitive_id: String,
        args: Vec<Term>,
        result_value_id: String,
        provenance: Provenance,
    },
    Receive {
        output_bytes_value_id: String,
        provenance: Provenance,
    },
    Send {
        bytes: Term,
        channel_id: String,
        provenance: Provenance,
    },
    Read {
        slot_id: String,
        output_value_id: String,
        provenance: Provenance,
    },
    Write {
        slot_id: String,
        value: Term,
        provenance: Provenance,
    },
    Erase {
        object_id: String,
        provenance: Provenance,
    },
    Emit {
        event_name: String,
        args: Vec<Term>,
        visibility: String,
        provenance: Provenance,
    },
    Accept {
        target_id: String,
        key: Term,
        #[serde(deserialize_with = "required_option")]
        peer: Option<Term>,
        provenance: Provenance,
    },
    Export {
        target_id: String,
        key: Term,
        provenance: Provenance,
    },
}

impl Step {
    pub fn provenance(&self) -> &Provenance {
        match self {
            Self::Assign { provenance, .. }
            | Self::Sample { provenance, .. }
            | Self::Invoke { provenance, .. }
            | Self::Receive { provenance, .. }
            | Self::Send { provenance, .. }
            | Self::Read { provenance, .. }
            | Self::Write { provenance, .. }
            | Self::Erase { provenance, .. }
            | Self::Emit { provenance, .. }
            | Self::Accept { provenance, .. }
            | Self::Export { provenance, .. } => provenance,
        }
    }

    pub fn defined_value(&self) -> Option<&str> {
        match self {
            Self::Assign {
                output_value_id, ..
            }
            | Self::Sample {
                output_value_id, ..
            }
            | Self::Read {
                output_value_id, ..
            } => Some(output_value_id),
            Self::Invoke {
                result_value_id, ..
            } => Some(result_value_id),
            Self::Receive {
                output_bytes_value_id,
                ..
            } => Some(output_bytes_value_id),
            _ => None,
        }
    }
}

record!(Binding {
    payload_name: String,
    value_id: String
});
record!(Arm { tag: String, bindings: Vec<Binding>, target_block: String });
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Terminator {
    Jump {
        target_block: String,
    },
    Branch {
        condition: Term,
        true_block: String,
        false_block: String,
    },
    Match {
        result_value_id: String,
        arms: Vec<Arm>,
    },
    Stop {
        reason: String,
    },
    Reject {
        target_ids: Vec<String>,
        reason: String,
    },
}
impl Terminator {
    pub fn successors(&self) -> Vec<&str> {
        match self {
            Self::Jump { target_block } => vec![target_block],
            Self::Branch {
                true_block,
                false_block,
                ..
            } => vec![true_block, false_block],
            Self::Match { arms, .. } => arms.iter().map(|a| a.target_block.as_str()).collect(),
            Self::Stop { .. } | Self::Reject { .. } => vec![],
        }
    }
}
record!(Block { id: String, steps: Vec<Step>, terminator: Terminator, provenance: Provenance });
record!(Role { id: String, parameter_value_ids: Vec<String>, entry_block: String, blocks: Vec<Block>, provenance: Provenance });
record!(Slot {
    id: String,
    type_id: String,
    scope: String,
    lifecycle_policy_id: String,
    provenance: Provenance
});
record!(Message {
    id: String,
    constructor_id: String,
    sender_role: String,
    receiver_role: String,
    encoding_id: String,
    provenance: Provenance
});
record!(Context {
    id: String,
    role_id: String,
    stage_id: String,
    purpose: String,
    recipe: Term,
    provenance: Provenance
});
record!(Target { id: String, role_id: String, stage_id: String, key_type_id: String, peer_mode: String, output_kind: String, property_definition_ids: Vec<String>, partnering_profile_id: String, exposure_profile_id: String, provenance: Provenance });
record!(Hole { id: String, object_path: String, expected_type_id: String, reason: String, blocked_obligation_ids: Vec<String>, provenance: Provenance });
record!(Protocol { id: String, case_kind: String, pinned_source_ids: Vec<String>, fragment_description: String, provenance: Provenance });
record!(Assessment {
    case_profile_id: String,
    obligation_ledger_id: String
});
record!(Model {
    format_version: String,
    protocol: Protocol,
    source_ids: Vec<String>,
    types: Vec<TypeDef>,
    primitives: Vec<Primitive>,
    constructors: Vec<Constructor>,
    encodings: Vec<Encoding>,
    values: Vec<ValueDecl>,
    slots: Vec<Slot>,
    messages: Vec<Message>,
    contexts: Vec<Context>,
    roles: Vec<Role>,
    targets: Vec<Target>,
    holes: Vec<Hole>,
    assessment: Assessment,
});

macro_rules! lookup {
    ($method:ident, $field:ident, $ty:ty) => {
        pub fn $method(&self, id: &str) -> Result<&$ty, String> {
            self.$field
                .iter()
                .find(|x| x.id == id)
                .ok_or_else(|| format!("unknown {}: {id}", stringify!($field)))
        }
    };
}
impl Model {
    lookup!(ty, types, TypeDef);
    lookup!(primitive, primitives, Primitive);
    lookup!(constructor, constructors, Constructor);
    lookup!(encoding, encodings, Encoding);
    lookup!(value, values, ValueDecl);
    lookup!(slot, slots, Slot);
    lookup!(role, roles, Role);
    lookup!(target, targets, Target);
    lookup!(hole, holes, Hole);
}
impl Role {
    lookup!(block, blocks, Block);
}
