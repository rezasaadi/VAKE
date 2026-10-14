import VAKE.Symbolic
namespace VAKE.Network

inductive Deducible (c : Contract) (r : Registry) (e : Environment) (roots : List Val) : Val → Prop where
  | root (v) : v ∈ roots → Deducible c r e roots v
  | literal (ty j v) : c.literal r ty j = .ok v → Deducible c r e roots v
  | atom (ty name length) : (r.types.find? (·.id == ty)).any (·.kind == "semantic") = true →
      Deducible c r e roots (.atom ty name "adversary" length)
  | record (ctor fs v) : (∀ n x, (n,x) ∈ fs → Deducible c r e roots x) →
      c.record r ctor fs = .ok v → Deducible c r e roots v
  | project (v name out) : Deducible c r e roots v → c.project v name = .ok out → Deducible c r e roots out
  | encode (id v out) : Deducible c r e roots v → c.encode r id v = .ok out → Deducible c r e roots out
  | decode (id v) : Deducible c r e roots (.encoded id v) → Deducible c r e roots v

  | bytesView (v) : Deducible c r e roots (.app "Bytes" "bytes_view" [v]) → Deducible c r e roots v
  | edhocView (ty op v) : op ∈ ["edhoc_bytes", "edhoc_splice", "edhoc_header_bytes", "edhoc_compact", "edhoc_full_id"] →
      Deducible c r e roots (.app ty op [v]) → Deducible c r e roots v
  | edhocConcat (a b v) : v ∈ [a,b] → Deducible c r e roots (.app "Bytes" "edhoc_concat" [a,b]) → Deducible c r e roots v
  | pure (pid args out) : (r.primitives.find? (·.id == pid)).any (·.mode == "pure_total") = true →
      (∀ x ∈ args, Deducible c r e roots x) →
      c.pure r e pid args = .ok out → Deducible c r e roots out
  | call (pid args counter tag payload counter' ty) :
      (∀ x ∈ args, Deducible c r e roots x) →
      c.invoke r e "adversary" pid args counter = .ok (tag, payload, counter') →
      (r.types.find? (·.id == ty)).any (fun t => t.kind == "result" && t.primitive == some pid) = true →
      Deducible c r e roots (.result ty pid tag payload)
  | payload (pid args counter tag payload counter' name v) :
      (∀ x ∈ args, Deducible c r e roots x) →
      c.invoke r e "adversary" pid args counter = .ok (tag, payload, counter') →
      (name, v) ∈ payload → Deducible c r e roots v

mutual
  inductive Recipe where
    | literal (ty json : String)
    | atom (ty name : String) (length : Option Nat)
    | signingKey (party : String)
    | publicKey (party : String)
    | signatureCredential (domain reference principal keyOwner : String)
    | kemSecretKey (party : String)
    | kemPublicKey (party : String)
    | kemCredential (domain reference principal keyOwner : String)
    | sent (index : Nat)
    | named (name : String)
    | known (value : Val)
    | field (record : Recipe) (name : String)
    | decode (bytes : Recipe)
    | record (constructor : String) (fields : RecipeFields)
    | encode (encoding : String) (record : Recipe)
    | call (primitive : String) (args : Recipes)
    deriving Repr, BEq, Inhabited
  inductive Recipes where
    | nil
    | cons (head : Recipe) (tail : Recipes)
    deriving Repr, BEq, Inhabited
  inductive RecipeFields where
    | nil
    | cons (name : String) (head : Recipe) (tail : RecipeFields)
    deriving Repr, BEq, Inhabited
end

structure RecipeState where
  counter : Nat
  additions : List Val := []
  required : List (List Val × Val) := []
  deriving Repr, BEq, Inhabited
def check (setup : Bool) (v : Val) (s : RecipeState) : Val × RecipeState :=
  (v, if setup then s else {s with required := s.required ++ [(s.additions, v)]})
def attackerCall (c : Contract) (r : Registry) (e : Environment) (pid : String)
    (args : List Val) (state : RecipeState) : Eval (Val × RecipeState) := do
  let (tag, payload, counter) ← c.invoke r e "adversary" pid args state.counter
  let p ← need "unknown primitive" (r.primitives.find? (·.id == pid))
  let v ← (if p.mode == "pure_total" then need "empty pure output" (payload.head?.map Prod.snd) else do
    let ty ← need "attacker call needs result type" (r.types.find? (fun t => t.kind == "result" && t.primitive == some pid))
    return Val.result ty.id pid tag payload)
  return (v, {state with counter, additions := state.additions ++ [v]})
mutual
  def recipe (c : Contract) (r : Registry) (e : Environment) (w : World) (setup : Bool)
      (state : RecipeState) : Recipe → Eval (Val × RecipeState)
    | .literal ty j => do return check setup (← c.literal r ty j) state
    | .atom ty n len => do
      if !(r.types.find? (·.id == ty)).any (·.kind == "semantic") then throw (.stuck "attacker atom requires semantic sort")
      let v := Val.atom ty n "adversary" (some (len.getD (Symbolic.width ty)))
      return (v, {state with additions := state.additions ++ [v]})
    | .signingKey p => do
      if e.interpretation == "kemtls_symbolic_v1" then throw (.stuck "unknown setup party")
      if !e.parties.contains p then throw (.stuck "unknown setup party")
      if e.interpretation == "edhoc_method0_suite0_v1" && !e.edhocSetup.signatureKeyOwners.contains p then throw (.stuck "unknown setup party")
      return check setup (Symbolic.signingKey p) state
    | .publicKey p => do
      if e.interpretation == "kemtls_symbolic_v1" then throw (.stuck "unknown setup party")
      if !e.parties.contains p then throw (.stuck "unknown setup party")
      if e.interpretation == "edhoc_method0_suite0_v1" && !e.edhocSetup.signatureKeyOwners.contains p then throw (.stuck "unknown setup party")
      return check setup (Symbolic.publicKey p) state
    | .kemSecretKey p => do
      if !e.kemKeyOwners.contains p then throw (.stuck "unknown KEM setup owner")
      return check setup (Symbolic.kemSecretKey p) state
    | .signatureCredential d ref principal owner => do
      let token : Credential := ⟨d, ref, principal, owner⟩
      if e.interpretation != "edhoc_method0_suite0_v1" then throw (.stuck "signature_credential requires P3 setup")
      if !e.edhocSetup.localCredentials.contains token then throw (.stuck "unknown local signature credential")
      let v := Symbolic.credentialValue token
      let additions := [v, Symbolic.stringVal "Label" d, Symbolic.stringVal "CredentialId" ref, Symbolic.stringVal "Principal" principal, Symbolic.publicKey owner]
      return check setup v {state with additions := state.additions ++ additions}
    | .kemPublicKey p => do
      if !e.kemKeyOwners.contains p then throw (.stuck "unknown KEM setup owner")
      return check setup (Symbolic.kemPublicKey p) state
    | .kemCredential d ref principal owner => do
      let token : Credential := ⟨d, ref, principal, owner⟩
      if !e.kemCredentials.contains token then throw (.stuck "unknown KEM setup credential")
      return check setup (Symbolic.kemCredentialValue token) state
    | .sent i => do return check setup (← need "sent index absent" w.sent[i]?) state
    | .named n => do return check setup (← need "unknown attacker name" (lookup w.names n)) state
    | .known v => .ok (v, {state with required := state.required ++ [(state.additions, v)]})
    | .field t f => do
      let (v, s) ← recipe c r e w false state t
      return check setup (← c.project v f) s
    | .decode t => do
      let (v, s) ← recipe c r e w false state t
      match v with
      | .encoded _ v => return check setup v s
      | _ => .error (.stuck "attacker decode: malformed bytes")
    | .record ctor fs => do
      let (vs, s) ← recipeFields c r e w state fs
      return check setup (← c.record r ctor vs) s
    | .encode id t => do
      let (v, s) ← recipe c r e w false state t
      return check setup (← c.encode r id v) s
    | .call pid args => do
      let (vs, s) ← recipes c r e w state args
      attackerCall c r e pid vs s
  def recipes (c : Contract) (r : Registry) (e : Environment) (w : World)
      (state : RecipeState) : Recipes → Eval (List Val × RecipeState)
    | .nil => .ok ([], state)
    | .cons t ts => do
      let (v, s) ← recipe c r e w false state t
      let (vs, s') ← recipes c r e w s ts
      return (v :: vs, s')
  def recipeFields (c : Contract) (r : Registry) (e : Environment) (w : World)
      (state : RecipeState) : RecipeFields → Eval (Store × RecipeState)
    | .nil => .ok ([], state)
    | .cons n t ts => do
      let (v, s) ← recipe c r e w false state t
      let (vs, s') ← recipeFields c r e w s ts
      return ((n, v) :: vs, s')
end
def parameters (c : Contract) (r : Registry) (e : Environment) (w : World)
    (state : RecipeState) : List (String × Recipe) → Eval (Store × RecipeState)
  | [] => .ok ([], state)
  | (n,t) :: ts => do
    let (v,s) ← recipe c r e w true state t
    let (vs,s') ← parameters c r e w s ts
    return ((n,v) :: vs, s')

def admitted (c : Contract) (r : Registry) (e : Environment) (w : World) (rs : RecipeState) : Prop :=
  ∀ extra v, (extra, v) ∈ rs.required → Deducible c r e (w.knowledge ++ extra) v

def applyRecipe (w : World) (s : RecipeState) : World :=
  {w with counter := s.counter, knowledge := w.knowledge ++ s.additions}
def initial (e : Environment) : World :=
  if e.interpretation == "kemtls_symbolic_v1" then
    {knowledge := e.kemKeyOwners.map Symbolic.kemPublicKey ++ e.kemCredentials.flatMap (fun c =>
      [Symbolic.kemCredentialValue c, Symbolic.stringVal "Label" c.domain, Symbolic.stringVal "CredentialId" c.reference,
        Symbolic.stringVal "Principal" c.principal, Symbolic.kemPublicKey c.keyOwner])}
  else {knowledge := (if e.interpretation == "edhoc_method0_suite0_v1" then e.edhocSetup.signatureKeyOwners else e.parties).map Symbolic.publicKey ++ e.credentials.flatMap (fun c =>
    [Symbolic.credentialValue c, Symbolic.stringVal "Label" c.domain, Symbolic.stringVal "CredentialId" c.reference,
      Symbolic.stringVal "Principal" c.principal, Symbolic.publicKey c.keyOwner])}

def kemOwned (party : String) (v : Val) : Bool :=
  match v with
  | .atom "KemSecretKey" owner "trusted_kem_setup" _ => owner == party
  | .record _ _ fs | .result _ _ _ fs => fs.attach.all (fun f => kemOwned party f.val.2)
  | .encoded _ x => kemOwned party x
  | .app _ "bytes_view" [x] => kemOwned party x
  | _ => true
termination_by v
decreasing_by
  all_goals simp_wf
  all_goals try omega
  all_goals first
    | have h := List.sizeOf_lt_of_mem f.property
      have h2 : sizeOf f.val = 1 + sizeOf f.val.1 + sizeOf f.val.2 := rfl
      omega
    | omega

def signatureOwned (party : String) (v : Val) : Bool :=
  match v with
  | .atom "SignatureSecretKey" owner "trusted_setup" _ => owner == party
  | .record _ _ fs | .result _ _ _ fs => fs.attach.all (fun f => signatureOwned party f.val.2)
  | .encoded _ x => signatureOwned party x
  | .app _ "bytes_view" [x] => signatureOwned party x
  | _ => true
termination_by v
decreasing_by
  all_goals simp_wf
  all_goals try omega
  all_goals first
    | have h := List.sizeOf_lt_of_mem f.property
      have h2 : sizeOf f.val = 1 + sizeOf f.val.1 + sizeOf f.val.2 := rfl
      omega
    | omega

def spawn (r : Registry) (e : Environment) (sid role party entry : String) (expected : List String)
    (params : Store) (w : World) : Eval World := do
  if sid == "adversary" then throw (.stuck "adversary is a reserved execution origin")
  if (lookup w.sessions sid).isSome then throw (.stuck "duplicate session instance")
  if !e.parties.contains party then throw (.stuck "unknown session party")
  if params.length != expected.length || !expected.all (fun n => (lookup params n).isSome) then
    throw (.stuck "session parameters differ from role parameters")
  for (n,v) in params do
    if e.interpretation == "kemtls_symbolic_v1" && !kemOwned party v then
      throw (.stuck "KEM setup secret belongs to another party")
    if e.interpretation == "edhoc_method0_suite0_v1" && !signatureOwned party v then
      throw (.stuck "KEM setup secret belongs to another party")
    if !(r.values.find? (·.id == n)).any (·.ty == v.typeId) then
      throw (.stuck "parameter type mismatch")
  let s : Session := {role, party, block := entry, locals := params, targets := (r.targets.filter (·.role == role)).map (fun t => (t.id, "pending"))}
  return appendEvent (updateSession w sid s)
    {session := some sid, role, kind := "spawn", visibility := "analysis", names := [party]}
def deliver (r : Registry) (e : Environment) (sid : String) (v : Val) (waiting : Bool) (w : World) : Eval World := do
  if v.typeId != "Bytes" then throw (.stuck "public delivery requires Bytes")
  let s ← need "unknown session" (lookup w.sessions sid)
  if waiting then
    return appendEvent (updateSession w sid {s with pending := some v})
      {session := some sid, role := s.role, kind := "deliver", visibility := "public", values := [v]}
  let complete := s.status == .stopped || (!s.targets.isEmpty && s.targets.all (fun t => t.2 == "accepted"))
  if e.phase == "reject_unexpected_preserve_completed" then
    let s' := if !complete && s.status == .active then
      {s with status := .rejected, locals := if e.interpretation == "edhoc_method0_suite0_v1" then [] else s.locals.filter (fun (n,_) => (r.values.find? (·.id == n)).any (·.storage == "parameter")), slots := [], pending := none, targets := s.targets.map (fun (n,t) => (n, if t == "pending" then "rejected" else t))}
      else s
    return appendEvent (updateSession w sid s')
      {session := some sid, role := s.role, kind := "unexpected_input_rejected", visibility := "public", names := [e.phase], values := [v, Symbolic.boolVal complete]}
  else
    let s' := if s.status == .active then {s with status := .stuck "unexpected input"} else s
    return appendEvent (updateSession w sid s')
      {session := some sid, role := s.role, kind := "unexpected_input_stuck", visibility := "analysis", values := [v]}
def remember (name : String) (v : Val) (w : World) : Eval World := do
  if (lookup w.names name).isSome then throw (.stuck "duplicate attacker recipe name")
  return appendEvent {w with names := put w.names name v, knowledge := w.knowledge ++ [v]}
    {session := none, kind := "attacker_compute", visibility := "public", names := [name], values := [v]}
def exportValues (w : World) (sid target : String) : List Val :=
  (w.history.filter (fun ev => ev.session == some sid && ev.kind == "export" && ev.names == [target])).flatMap (·.values)
def liveValues (r : Registry) (s : Session) : List Val :=
  ((s.locals.filter (fun (n,_) => (r.values.find? (·.id == n)).any (·.storage == "local"))) ++ s.slots).map Prod.snd
def expose (r : Registry) (e : Environment) (kind sid target : String) (w : World) : Eval World := do
  if !e.exposures.contains kind then throw (.stuck ("exposure disabled: " ++ kind))
  if kind == "corrupt" then
    if !e.parties.contains sid then throw (.stuck "unknown party")
    let setup := if e.interpretation == "kemtls_symbolic_v1" then
      (if e.kemKeyOwners.contains sid then [Symbolic.kemSecretKey sid] else [])
      else if e.interpretation == "edhoc_method0_suite0_v1" && !e.edhocSetup.signatureKeyOwners.contains sid then [] else [Symbolic.signingKey sid]
    let vs := setup ++ ((lookup w.persistent sid).getD []).map Prod.snd
    return appendEvent {w with knowledge := w.knowledge ++ vs}
      {session := none, kind, visibility := "public", names := [sid], values := vs}
  let s ← need "unknown session" (lookup w.sessions sid)
  let vs := if kind == "reveal_export" then exportValues w sid target else liveValues r s
  if kind == "reveal_export" && vs.isEmpty then throw (.stuck "no exported target handle")
  return appendEvent {w with knowledge := w.knowledge ++ vs}
    {session := some sid, role := s.role, kind, visibility := "public", names := if kind == "reveal_export" then [target] else [], values := vs}
end VAKE.Network
