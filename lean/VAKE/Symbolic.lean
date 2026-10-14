import VAKE.Common
import VAKE.EDHOC
namespace VAKE.Symbolic
def width (ty : String) : Nat := if ty == "Signature" then 64 else 32
def stringVal (ty s : String) : Val := .literal ty (Lean.Json.str s).compress
def boolVal (b : Bool) : Val := .literal "Bool" (if b then "true" else "false")
def string? : Val → Option String
  | .literal _ j => (Lean.Json.parse j).toOption.bind (fun j => j.getStr?.toOption)
  | _ => none
def natural? : Val → Option Nat
  | .literal "Nat" j => (Lean.Json.parse j).toOption.bind (fun j => j.getNat?.toOption)
  | _ => none
def appArgs (v : Val) (op : String) : Option (List Val) :=
  match v with
  | .app _ actual args => if actual == op then some args else none
  | _ => none
def signingKey (party : String) : Val := .atom "SignatureSecretKey" party "trusted_setup" (some 32)
def publicKey (party : String) : Val := .app "SignaturePublicKey" "sig_pk" [signingKey party]
def kemSecretKey (party : String) : Val := .atom "KemSecretKey" party "trusted_kem_setup" (some 32)
def kemPublicKey (party : String) : Val := .app "KemPublicKey" "kem_pk" [kemSecretKey party]
def kemCredentialValue (c : Credential) : Val :=
  .app "KemCredential" "kem_credential" [stringVal "Label" c.domain, stringVal "CredentialId" c.reference,
    stringVal "Principal" c.principal, kemPublicKey c.keyOwner]
def credentialValue (c : Credential) : Val :=
  .app "Credential" "credential" [stringVal "Label" c.domain, stringVal "CredentialId" c.reference,
    stringVal "Principal" c.principal, publicKey c.keyOwner]
def fresh (ty sid op : String) (counter : Nat) : Val :=
  .atom ty (op ++ ":" ++ toString (counter + 1)) ("session:" ++ sid) (some (width ty))

def literal (r : Registry) (ty json : String) : Eval Val := do
  let t ← need "unknown literal type" (r.types.find? (·.id == ty))
  let j ← (Lean.Json.parse json).mapError Fault.stuck
  let valid : Bool := if ty == "Bool" then j.getBool?.isOk
    else if ty == "Nat" then match j.getNat? with
      | .ok n => n ≤ 18446744073709551615
      | .error _ => false
    else ["Bytes", "Principal", "RoleId", "SessionId", "SuiteId", "CredentialId", "Label"].contains ty && j.getStr?.isOk
  if t.kind == "base" && valid then return .literal ty j.compress
  else .error (.stuck "invalid literal sort/value")
def record (r : Registry) (ctor : String) (fs : Store) : Eval Val := do
  let d ← need "unknown constructor" (r.constructors.find? (·.id == ctor))
  if fs.map (fun (n, v) => (n, v.typeId)) == d.fields then return .record d.ty ctor fs
  else .error (.stuck "record layout/type mismatch")
def project (v : Val) (field : String) : Eval Val :=
  match v with
  | .record _ _ fs | .result _ _ _ fs => need ("field absent: " ++ field) (lookup fs field)
  | _ => .error (.stuck "projection requires record")
def encode (r : Registry) (id : String) (v : Val) : Eval Val := do
  let d ← need "unknown encoding" (r.encodings.find? (·.id == id))
  match v with
  | .record .. =>
    if d.types.contains v.typeId then return .encoded id v
    else .error (.stuck "encoding type mismatch")
  | _ => .error (.stuck "encoding requires record")
def wellSized (v : Val) : Bool :=
  match v with
  | .atom ty _ _ length => length.getD (width ty) == width ty
  | .literal _ _ => (string? v).all (fun s => s.utf8ByteSize ≤ 4096)
  | .record _ _ fs => fs.attach.all (fun f => wellSized f.val.2)
  | .encoded _ v => wellSized v
  | _ => true
termination_by v
decreasing_by
  all_goals simp_wf
  all_goals try omega
  have h := List.sizeOf_lt_of_mem f.property
  have h2 : sizeOf f.val = 1 + sizeOf f.val.1 + sizeOf f.val.2 := rfl
  omega

def p3WellSized (v : Val) : Bool :=
  match v with
  | .atom ty _ _ _ => if ty == "AeadCiphertext" || ty == "Bytes" then true else wellSized v
  | .record _ _ fs => fs.attach.all (fun f => p3WellSized f.val.2)
  | .encoded _ v => p3WellSized v
  | _ => wellSized v
termination_by v
decreasing_by
  all_goals simp_wf
  all_goals try omega
  have h := List.sizeOf_lt_of_mem f.property
  have h2 : sizeOf f.val = 1 + sizeOf f.val.1 + sizeOf f.val.2 := rfl
  omega

def ordered (vs : List Val) : List Val := Val.sort vs
def xorTerms (v : Val) : List Val :=
  if string? v == some "" then [] else (appArgs v "xor").getD [v]
def xorValue (a b : Val) : Val :=
  let parity := (xorTerms a ++ xorTerms b).foldl
    (fun acc v => if acc.contains v then acc.filter (· != v) else v :: acc) []
  match ordered parity with
  | [] => stringVal "Bytes" ""
  | [v] => v
  | vs => .app "Bytes" "xor" vs

def invoke (r : Registry) (e : Environment) (sid pid : String) (args : List Val) (counter : Nat) :
    Eval (String × Store × Nat) := do
  let p ← need "unknown primitive" (r.primitives.find? (·.id == pid))
  if args.map Val.typeId != p.inputs.map (fun x => x.2.1) then
    throw (.stuck ("primitive argument type mismatch: " ++ pid))
  let ok ← need "contract no ok outcome" (lookup p.outcomes "ok")
  let out := (ok.head?.map Prod.snd).getD ""
  let result : Eval (String × List Val × Nat) := match p.op, args with
    | "fresh", [] => .ok ("ok", [fresh out sid "sample" counter], counter + 1)
    | "hash", _ | "extract", _ | "expand", _ | "sign", _ | "mac", _ =>
      .ok ("ok", [.app out p.op args], counter)
    | "tls_extract", _ | "tls_expand", _ | "bytes_view", _ |
      "tls_record_nonce", _ | "tls_record_aad", _ =>
      .ok ("ok", [.app out p.op args], counter)
    | "verify", [pk, msg, sig] =>
      let valid : Bool := match appArgs sig "sign" with
        | some [sk, m] => pk == .app "SignaturePublicKey" "sig_pk" [sk] && m == msg
        | _ => false
      .ok (if valid then "ok" else "invalid", [], counter)
    | "kem_keygen", [] =>
      let sk := fresh "KemSecretKey" sid "kem_keygen" counter
      .ok ("ok", [.app "KemPublicKey" "kem_pk" [sk], sk], counter + 1)
    | "kem_encap", [pk] =>
      let random := fresh "SharedSecret" sid "kem_encap_randomness" counter
      .ok ("ok", [.app "KemCiphertext" "kem_ct" [pk, random], .app "SharedSecret" "kem_secret" [pk, random]], counter + 1)
    | "kem_decap", [sk, ct] =>
      let error := e.correctnessErrorSessions.contains sid
      let pk := Val.app "KemPublicKey" "kem_pk" [sk]
      match appArgs ct "kem_ct" with
      | some [pk', random] =>
        if pk == pk' && !error then .ok ("ok", [.app "SharedSecret" "kem_secret" [pk, random]], counter)
        else if p.failure == "implicit_rejection" then
          .ok ("ok", [.app "SharedSecret" (if error then "kem_correctness_error" else "kem_reject") args], counter)
        else .ok ("invalid", [], counter)
      | _ => if p.failure == "implicit_rejection" then
          .ok ("ok", [.app "SharedSecret" (if error then "kem_correctness_error" else "kem_reject") args], counter)
        else .ok ("invalid", [], counter)
    | "decode", [.encoded id v] =>
      if ((r.encodings.find? (·.id == id)).any (fun d => d.types.contains out)) && v.typeId == out &&
          (if e.interpretation == "edhoc_method0_suite0_v1" then p3WellSized v else wellSized v) &&
          (e.interpretation != "edhoc_method0_suite0_v1" || (EDHOC.length r (.encoded id v)).isSome) then
        .ok ("ok", [v], counter) else .ok ("invalid", [], counter)
    | "decode", [_] => .ok ("invalid", [], counter)
    | "credential", [d, ref, principal] =>
      match e.credentials.filter (fun c => string? d == some c.domain && string? ref == some c.reference &&
        string? principal == some c.principal) with
      | [c] => .ok ("ok", [publicKey c.keyOwner], counter)
      | _ => .ok ("invalid", [], counter)
    | "credential_resolve", [d, ref, index] => do
      let n ← need "index not natural" (natural? index)
      match (e.credentials.filter (fun c => string? d == some c.domain && string? ref == some c.reference))[n]? with
      | some c => return ("ok", [credentialValue c], counter)
      | none => return ("not_found", [], counter)
    | "validate_credential", [token, domain, principal] =>
      match e.credentials.find? (fun c => credentialValue c == token && string? domain == some c.domain && string? principal == some c.principal) with
      | some c => .ok ("ok", [publicKey c.keyOwner], counter)
      | none => .ok ("invalid", [], counter)
    | "validate_kem_credential", [token, domain, principal] =>
      match e.kemCredentials.find? (fun c => kemCredentialValue c == token &&
        string? domain == some c.domain && string? principal == some c.principal) with
      | some c => .ok ("ok", [kemPublicKey c.keyOwner], counter)
      | none => .ok ("invalid", [], counter)
    | "eq", [a, b] => .ok ("ok", [boolVal (a == b)], counter)
    | "and", [a, b] => do
      let av ← boolean a
      let bv ← boolean b
      return ("ok", [boolVal (av && bv)], counter)
    | "check_mac", [key, msg, tag] => .ok (if tag == .app "MacTag" "mac" [key, msg] then "ok" else "invalid", [], counter)
    | "dh_keygen", [] =>
      let sk := fresh "DhSecret" sid "dh_keygen" counter
      .ok ("ok", [.app "DhPublic" "dh_pk" [sk], sk], counter + 1)
    | "dh_validate", [pk] => .ok (if (appArgs pk "dh_pk").isSome then ("ok", [pk], counter) else ("invalid", [], counter))
    | "dh_shared", [sk, pk] =>
      match appArgs pk "dh_pk" with
      | some [other] => .ok ("ok", [.app "SharedSecret" "dh_shared" (ordered [sk, other])], counter)
      | _ => .ok ("invalid", [], counter)
    | "aead_seal", _ => .ok ("ok", [.app "AeadCiphertext" "aead" args], counter)
    | "aead_open", [k, n, ct, a] =>
      match appArgs ct "aead" with
      | some [k', n', m, a'] => if k == k' && n == n' && a == a' then .ok ("ok", [m], counter) else .ok ("invalid", [], counter)
      | _ => .ok ("invalid", [], counter)
    | "xor", [a, b] => .ok ("ok", [xorValue a b], counter)
    | _, _ => if p.op.startsWith "edhoc_" then do
        let (tag, vs) ← EDHOC.invoke r e p.op out args
        return (tag, vs, counter)
      else .error (.stuck ("unsupported contract/arity: " ++ p.op))
  let (tag, values, counter') ← result
  let payload ← need "backend outcome undeclared" (lookup p.outcomes tag)
  if payload.length != values.length then throw (.stuck "backend payload arity mismatch")
  return (tag, (payload.map Prod.fst).zip values, counter')

def pure (r : Registry) (e : Environment) (pid : String) (args : List Val) : Eval Val := do
  let (_, payload, _) ← invoke r e "pure" pid args 0
  need "pure result absent" (payload.head?.map Prod.snd)
def contract : Contract := ⟨literal, record, project, encode, pure, invoke⟩

end VAKE.Symbolic
