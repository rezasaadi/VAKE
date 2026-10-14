# VAKE input language

VAKE accepts typed protocol models encoded as JSON with `format_version: "0.1"`. Changing a file suffix does not change the parser. Begin with [the public-message example](../examples/public_message.json) or [the nonce exchange](../examples/nonce_exchange.json). The complete field definitions are in [src/ir.rs](../src/ir.rs).

## Model structure

A model contains `protocol`, `types`, `primitives`, `constructors`, `encodings`, `values`, `slots`, `messages`, `contexts`, `roles`, `targets`, and `holes`. Each role declares parameters, an entry block, and blocks containing ordered steps followed by a terminator.

Operational fields are mandatory, including explicit `null` for absent `primitive_ref` and `peer` where required. Evidence metadata has defaults at specific schema sites: provenance, source IDs, selected protocol descriptions, assessment, primitive security/cost metadata, and intended visibility. Explicit metadata is still checked. Defaults in [src/admission.rs](../src/admission.rs) never descend into literal data.

## Terms, steps, and control flow

| Term | Meaning |
|---|---|
| `ref` | A role-owned value with a dominating live definition |
| `literal` | A Bool, Nat, or string-valued base-sort value; cannot fabricate a semantic secret |
| `record` | A record with declared, ordered constructor fields |
| `project` | A declared field projection |
| `encode` | A record accepted by a declared codec, producing Bytes |
| `apply` | A pure deterministic primitive with a single output |
| `hole` | An explicit unresolved term with a declared expected type |

Steps are `assign`, `sample`, `invoke`, `receive`, `send`, `read`, `write`, `erase`, `emit`, `accept`, and `export`. Terminators are `jump`, `branch`, `match`, `stop`, and `reject`. Branch conditions have type Bool. Match arms bind declared result payloads; missing arms are legal but can produce unhandled operational outcomes.

Base sorts include Bytes, Bool, Nat, Principal, RoleId, SessionId, SuiteId, CredentialId, and Label. Semantic sorts include Nonce, cryptographic key/result sorts, and user nominal sorts. Equality of types is nominal. Record/result payload types and control-flow graphs must be acyclic.

The checker enforces unique identifiers, registry references, constructor layout, ownership, and single definitions. A merge retains only values available on every incoming path. Erasure removes a live local name; previously created aliases can remain valid. A value's declaration does not itself make that value live.

## Backend contracts and profiles

Backend contract admission is separate from typing. The supported operations are `fresh`, `hash`, `extract`, `expand`, `bytes_view`, `sign`, `verify`, `kem_keygen`, `kem_encap`, `kem_decap`, `decode`, `credential`, `credential_resolve`, `validate_credential`, `eq`, `and`, `mac`, `check_mac`, `dh_keygen`, `dh_validate`, `dh_shared`, `aead_seal`, `aead_open`, and `xor`. [src/contracts.rs](../src/contracts.rs) enforces exact signatures, modes, failure tags, and argument positions. Adding an `Op.*` name does not implement an operation.

Only `fixture_tlv` with `FixtureEncodingInverse` and optional `FixtureEncodingInjective` is admitted. This specifies a symbolic codec contract, not a binary implementation. Profiles require `schema_version: "1.0"` and `interpretation: "restricted_symbolic_v1"`. Phase policies, exposure interfaces, parties, credentials, and KEM correctness settings are checked by [src/profile.rs](../src/profile.rs).

## Rejected and open inputs

Malformed JSON, unknown fields/variants, and duplicate keys at any depth are rejected. [Negative examples](../examples/README.md#rejected-inputs) illustrate syntax, typing, control-flow, contract, and profile failures.

Models with declared holes can pass typing with an `OPEN_OBLIGATION` result and can be exported. Resolve those holes before requesting closed-model certificates. Label literals are supported by the general model language, although the nonce-specific concrete execution demo avoids them.

For result interpretation and example-specific checks, read [the README](../README.md#what-vake-checks) and [limitations](limitations.md).
