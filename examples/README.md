# VAKE examples

Use a bundled model to learn the schema and workflow before writing a custom model.

| Input | Demonstration |
|---|---|
| `public_message.json` | Minimal public byte message |
| `nonce_exchange.json` | Two-role nonce exchange, local certificate, honest global trace, and malformed-message rejection |
| `dh_exchange.json` | Unauthenticated Diffie–Hellman exchange with accept targets; checked honest key agreement and a man-in-the-middle execution in which the adversary computes both accepted keys |
| `signed_dh_exchange.json` | DH exchange with signed shares; checked honest agreement and two share substitutions that fail signature verification, with no key accepted |
| `signature_check.json` | Signature-construction lemma and separately labeled executable verification observations |
| `revisions/signed_dh_unchecked_signature.json` | One-line edit of the signed DH model (responder continues after a failed signature check) and its rebound scenario file; used by `scripts/revision_demo.py`, where the attack scenarios' rejection certificates are expected to fail |
| `scenarios/*.scenarios.json` | Concrete executions and final-state claims, bound by hash to a model and profile ([format](../docs/scenarios.md)) |
| `restricted_symbolic_v1.profile.json` | Supported profile for export and verification |

From the repository root:

```bash
./target/debug/vake check examples/public_message.json
./target/debug/vake verify examples/public_message.json \
  --profile examples/restricted_symbolic_v1.profile.json \
  --out reports/public-message-verification
```

On Windows, use `target\debug\vake.exe`. Choose a fresh output directory. Use `vake demo` or the browser to check the bundled concrete executions; see [scenarios](../docs/scenarios.md).

The nonce is public. Erasing a local value does not remove packets, sent bytes, or existing aliases. These examples do not prove authentication, secrecy, or secure erasure. The DH man-in-the-middle scenario is a checked execution showing that this unauthenticated model accepts keys the adversary computes.

## Rejected inputs

Run negative models with `vake check`. `unsupported_profile.json` is a profile and must instead be supplied through `--profile` during export or verification.

| File under `negative/` | Expected category |
|---|---|
| `malformed_syntax.json` | `PARSE_ERROR` |
| `duplicate_nested_key.json` | `PARSE_ERROR` |
| `unknown_instruction.json` | `PARSE_ERROR` |
| `duplicate_declaration.json` | `TYPE_ERROR` |
| `undefined_variable.json` | `TYPE_ERROR` |
| `type_mismatch.json` | `TYPE_ERROR` |
| `invalid_cfg.json` | `TYPE_ERROR` |
| `invalid_crypto_contract.json` | `UNSUPPORTED` |
| `unsupported_law.json` | `UNSUPPORTED` |
| `unsupported_profile.json` | `UNSUPPORTED` |

These cases are expected to return exit code `1`. Their rejection is successful negative-test behavior, not successful verification of a protocol. The frontend test suite checks the categories and additional malformed cases.

See [the input-language guide](../docs/language.md) for terms, steps, and backend contracts.
