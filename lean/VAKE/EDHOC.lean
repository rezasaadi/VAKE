import VAKE.Common

namespace VAKE.EDHOC

def string? : Val → Option String
  | .literal _ j => (Lean.Json.parse j).toOption.bind (fun j => j.getStr?.toOption)
  | _ => none
def natural? : Val → Option Nat
  | .literal "Nat" j =>
    let cs := j.toList
    if cs.isEmpty || (cs.length > 1 && cs.head? == some '0') then none
    else cs.foldlM (fun n c => if '0' ≤ c && c ≤ '9' then some (n * 10 + c.toNat - '0'.toNat) else none) 0
  | _ => none
def str (ty s : String) : Val := .literal ty (Lean.Json.str s).compress
def nat (n : Nat) : Val := .literal "Nat" (toString n)
def bool (b : Bool) : Val := .literal "Bool" (if b then "true" else "false")
def appArgs (v : Val) (op : String) : Option (List Val) :=
  match v with
  | .app _ actual args => if actual == op then some args else none
  | _ => none
def digit (c : Char) : Option Nat :=
  if '0' ≤ c && c ≤ '9' then some (c.toNat - '0'.toNat)
  else if 'a' ≤ c && c ≤ 'f' then some (c.toNat - 'a'.toNat + 10)
  else if 'A' ≤ c && c ≤ 'F' then some (c.toNat - 'A'.toNat + 10) else none
def parseHex : List Char → Option (List Nat)
  | [] => some []
  | a :: b :: rest => do return (16 * (← digit a) + (← digit b)) :: (← parseHex rest)
  | _ => none

def octets (v : Val) : Option (List Nat) := match v with
  | .literal _ j =>
    let cs := j.toList
    if cs.head? == some '"' && cs.getLast? == some '"' && cs.length ≥ 2 then
      parseHex ((cs.drop 1).take (cs.length - 2)) else none
  | _ => none
def head (n : Nat) : Nat := if n < 24 then 1 else if n ≤ 255 then 2 else if n ≤ 65535 then 3 else if n ≤ 4294967295 then 5 else 9
def bstr (n : Nat) : Nat := head n + n
def compactLength (v : Val) : Option Nat := do
  let xs ← appArgs v "edhoc_compact"
  let x ← xs.head?
  let bs ← octets x
  return if bs.length == 1 && bs.any (fun b => b ≤ 23 || (32 ≤ b && b ≤ 55)) then 1 else bstr bs.length

mutual

  def lengthFuel (r : Registry) : Nat → Val → Option Nat
    | 0, _ => none
    | fuel+1, v => match v with
      | .literal ty _ => if ty == "Bytes" || ty == "CredentialId" then (octets v).map List.length else none
      | .encoded id (.record _ _ fs) => do
        let e ← r.encodings.find? (·.id == id)
        if !["edhoc_sequence", "edhoc_array"].contains e.family then none else do
          let widths ← fs.mapM (fun f => itemFuel r fuel f.2)
          return (if e.family == "edhoc_array" then head fs.length else 0) + widths.foldl (· + ·) 0
      | .atom ty _ _ len => if ["Bytes", "DhPublic", "Signature", "HashDigest", "AeadCiphertext"].contains ty then len else none
      | .app _ op args => match op, args with
        | "edhoc_bytes", [x] | "edhoc_splice", [x] => lengthFuel r fuel x
        | "edhoc_header_bytes", [x] => itemFuel r fuel x
        | "edhoc_concat", [x,y] => do return (← lengthFuel r fuel x) + (← lengthFuel r fuel y)
        | "hash", [_] | "dh_pk", [_] => some 32
        | "sign", [_,_] => some 64
        | "edhoc_expand", [_,_,n] | "edhoc_zero", [n] => natural? n
        | "aead", [_,_,m,_] => (lengthFuel r fuel m).map (· + 8)
        | "xor", x :: xs => do
          let n ← lengthFuel r fuel x
          if xs.all (fun y => lengthFuel r fuel y == some n) then some n else none
        | _, _ => none
      | _ => none
  def itemFuel (r : Registry) : Nat → Val → Option Nat
    | 0, _ => none
    | fuel+1, v => match v.typeId with
      | "Nat" => (natural? v).map head
      | "Bool" => some 1
      | "Label" => do
        let s ← string? v
        if s.utf8ByteSize > 128 then none else some (head s.utf8ByteSize + s.utf8ByteSize)
      | "CompactId" => compactLength v
      | "CborSplice" => lengthFuel r fuel v
      | "CoseHeader" => do
        let xs ← appArgs v "edhoc_full_id"
        let bs ← octets (← xs.head?)
        return 2 + bstr bs.length
      | "Credential" => do
        let xs ← appArgs v "credential"
        let subject ← string? (← xs[2]?)
        let kid ← octets (← xs[1]?)
        return 12 + head subject.utf8ByteSize + subject.utf8ByteSize + bstr kid.length + bstr 32
      | "Bytes" | "HashDigest" | "DhPublic" | "Signature" | "AeadCiphertext" => (lengthFuel r fuel v).map bstr
      | _ => none
end
def length (r : Registry) (v : Val) : Option Nat := lengthFuel r 10000 v

def ordered (xs : List Val) : List Val := Val.sort xs
def xorValue (n : Nat) (a b : Val) : Val :=
  let terms := (appArgs a "xor").getD [a] ++ (appArgs b "xor").getD [b]
  let parity := terms.foldl (fun acc v => if (appArgs v "edhoc_zero").isSome then acc
    else if acc.contains v then acc.filter (· != v) else v :: acc) []
  match ordered parity with
  | [] => .app "Bytes" "edhoc_zero" [nat n]
  | [v] => v
  | xs => .app "Bytes" "xor" xs
def signingKey (p : String) : Val := .atom "SignatureSecretKey" p "trusted_setup" (some 32)
def publicKey (p : String) : Val := .app "SignaturePublicKey" "sig_pk" [signingKey p]
def credential (c : Credential) : Val := .app "Credential" "credential"
  [str "Label" c.domain, str "CredentialId" c.reference, str "Principal" c.principal, publicKey c.keyOwner]
def goodSecret : Val → Bool
  | .atom "DhSecret" n _ len => n != "all_zero" && len.getD 32 == 32
  | _ => true

def invoke (r : Registry) (e : Environment) (op out : String) (args : List Val) : Eval (String × List Val) := do
  let invalid := ("invalid", [])
  match op, args with
  | "edhoc_extract", _ => return ("ok", [.app out op args])
  | "edhoc_expand", [_,info,len] =>
    let n ← need "invalid EDHOC output length" (natural? len)
    if n == 0 || n > 8160 || (out == "AeadKey" && n != 16) || (out == "AeadNonce" && n != 13) || (out == "SessionKey" && n != 32) then
      throw (.stuck "EDHOC output length outside selected contract")
    match info with
    | .encoded id (.record _ _ [(_,label),(_,context),(_,size)]) =>
      if (r.encodings.find? (·.id == id)).any (·.family == "edhoc_sequence") && label.typeId == "Nat" && context.typeId == "Bytes" && natural? size == some n then
        return ("ok", [.app out op args])
      else throw (.stuck "EDHOC info label/context/length mismatch")
    | _ => throw (.stuck "EDHOC Expand requires encoded info")
  | "edhoc_bytes", [_] | "edhoc_splice", [_] | "edhoc_header_bytes", [_] => return ("ok", [.app out op args])
  | "edhoc_length", [x] => return ("ok", [nat (← need "unknown EDHOC byte length" (length r x))])
  | "edhoc_concat", [x,y] =>
    let _ ← need "unknown EDHOC byte length" (length r x)
    let _ ← need "unknown EDHOC byte length" (length r y)
    return ("ok", [.app out op args])
  | "edhoc_split_m2", [.app _ "edhoc_concat" [.app _ "edhoc_bytes" [pk],ct]] =>
    if pk.typeId == "DhPublic" && length r pk == some 32 && (length r ct).isSome then return ("ok", [pk,ct]) else return invalid
  | "edhoc_split_m2", [_] => return invalid
  | "edhoc_compact_id", [x] | "edhoc_compact_connection", [x] =>
    let bs ← need "invalid EDHOC hexadecimal octets" (octets x)
    if (op == "edhoc_compact_id" && (bs.isEmpty || bs.length > 32)) || (op == "edhoc_compact_connection" && bs.length > 8) then
      throw (.stuck "identifier outside selected bound")
    return ("ok", [.app out "edhoc_compact" args])
  | "edhoc_full_id", [x] =>
    let bs ← need "invalid EDHOC hexadecimal octets" (octets x)
    if bs.isEmpty || bs.length > 32 then throw (.stuck "kid outside selected bound")
    return ("ok", [.app out op args])
  | "edhoc_reconstruct_id", [.app _ "edhoc_compact" [kid]] =>
    match octets kid, string? kid with
    | some bs, some s =>
      if bs.isEmpty || bs.length > 32 then return invalid
      else return ("ok", [.app out "edhoc_full_id" [str "CredentialId" s]])
    | _, _ => return invalid
  | "edhoc_reconstruct_id", [_] => return invalid
  | "edhoc_credential_resolve", [d,.app _ "edhoc_full_id" [kid]] =>
    match e.credentials.filter (fun c => string? d == some c.domain && string? kid == some c.reference) with
    | [] => return ("not_found", [])
    | [c] => return ("ok", [credential c])
    | _ => return ("ambiguous", [])
  | "edhoc_credential_resolve", [_,_] => return ("not_found", [])
  | "edhoc_xor", [x,y] =>
    match length r x, length r y with
    | some n, some k => if n == k && n ≤ 8160 then return ("ok", [xorValue n x y]) else return invalid
    | _, _ => return invalid
  | "edhoc_empty", [x] => return if length r x == some 0 then ("ok", []) else invalid
  | "edhoc_validate_connection", [.app _ "edhoc_compact" [x]] =>
    return if (octets x).any (fun bs => bs.length ≤ 8) then ("ok", []) else invalid
  | "edhoc_validate_connection", [_] => return invalid
  | "edhoc_is_error", [x] =>
    let yes := match x with
      | .encoded id (.record _ _ [(_,code),_]) =>
        (r.encodings.find? (·.id == id)).any (·.family == "edhoc_sequence") && code.typeId == "Nat"
      | _ => false
    return ("ok", [bool yes])
  | "edhoc_dh_shared", [sk,.app _ "dh_pk" [other]] =>
    if goodSecret sk && goodSecret other then return ("ok", [.app "SharedSecret" "dh_shared" (ordered [sk,other])]) else return invalid
  | "edhoc_dh_shared", [_,_] => return invalid
  | _, _ => throw (.stuck ("unsupported EDHOC operation/arity: " ++ op))
end VAKE.EDHOC
