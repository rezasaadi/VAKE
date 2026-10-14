import VAKE.Source.Syntax
namespace VAKE.Source
mutual
  def eval (c : Contract) (r : Registry) (e : Environment) (locals : Store) : Term → Eval Val
    | .ref v => need ("unavailable value: " ++ v) (lookup locals v)
    | .literal t j => c.literal r t j
    | .record k fs => do c.record r k (← evalFields c r e locals fs)
    | .project t f => do c.project (← eval c r e locals t) f
    | .encode k t => do c.encode r k (← eval c r e locals t)
    | .apply p a => do c.pure r e p (← evalArgs c r e locals a)
    | .hole h _ => .error (.hole h)
  def evalArgs (c : Contract) (r : Registry) (e : Environment) (locals : Store) : Args → Eval (List Val)
    | .nil => .ok []
    | .cons t ts => do
      let v ← eval c r e locals t
      let vs ← evalArgs c r e locals ts
      return v :: vs
  def evalFields (c : Contract) (r : Registry) (e : Environment) (locals : Store) : Fields → Eval Store
    | .nil => .ok []
    | .cons n t ts => do
      let v ← eval c r e locals t
      let vs ← evalFields c r e locals ts
      return (n, v) :: vs
end
def evalPeer (c : Contract) (r : Registry) (e : Environment) (l : Store) : Option Term → Eval (List Val)
  | none => .ok []
  | some t => do return [← eval c r e l t]

def instruction (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (i : Instruction) : Eval (World × Session × Event) := do
  let event := fun k v ns vs => ({session := some sid, role := s.role, kind := k, visibility := v, names := ns, values := vs, location := loc} : Event)
  match i with
  | .assign o t =>
    let v ← eval c r e s.locals t
    return (w, {s with locals := put s.locals o v}, event "assign" "analysis" [o] [v])
  | .sample o g =>
    let (_, payload, counter) ← c.invoke r e sid g [] w.counter
    let v ← need "empty generator payload" (payload.head?.map Prod.snd)
    return ({w with counter}, {s with locals := put s.locals o v}, event "sample" "analysis" [o] [v])
  | .invoke p a o =>
    let vs ← evalArgs c r e s.locals a
    let (tag, payload, counter) ← c.invoke r e sid p vs w.counter
    let decl ← need "unknown result variable" (r.values.find? (·.id == o))
    let v := Val.result decl.ty p tag payload
    return ({w with counter}, {s with locals := put s.locals o v}, event "invoke" "analysis" [p, tag] (v :: vs))
  | .receive o =>
    let v ← need "no delivery" s.pending
    return (w, {s with locals := put s.locals o v, pending := none}, event "receive" "analysis" [o] [v])
  | .send t channel =>
    let v ← eval c r e s.locals t
    return ({w with knowledge := w.knowledge ++ [v], sent := w.sent ++ [v]}, s, event "send" "public" [channel] [v])
  | .read slot o =>
    let v ← readSlot r w s slot
    return (w, {s with locals := put s.locals o v}, event "read" "analysis" [slot] [v])
  | .write slot t =>
    let v ← eval c r e s.locals t
    let (w', s') ← writeSlot r w s slot v
    return (w', s', event "write" "analysis" [slot] [v])
  | .erase o =>
    let (w', s') := eraseObject r w s o
    return (w', s', event "erase" "analysis" [o] [])
  | .emit n a vis =>
    let vs ← evalArgs c r e s.locals a
    return ({w with knowledge := if vis == "public" then w.knowledge ++ vs else w.knowledge}, s,
      event "emit" vis [n] vs)
  | .accept t k p =>
    targetAllowed s t
    let key ← eval c r e s.locals k
    let peer ← evalPeer c r e s.locals p
    return (w, {s with targets := put s.targets t "accepted"}, event "accept" "local" [t] (key :: peer))
  | .exportKey t k =>
    targetAllowed s t
    let key ← eval c r e s.locals k
    return (w, s, event "export" "local" [t] [key])

def bindPayload (locals payload : Store) : List (String × String) → Eval Store
  | [] => .ok locals
  | (name, output) :: rest => do
    let v ← need ("payload unavailable: " ++ name) (lookup payload name)
    bindPayload (put locals output v) payload rest

def terminator (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (t : Terminator) : Eval (World × Session × Event) := do
  let event := fun k ns vs => ({session := some sid, role := s.role, kind := k, visibility := "analysis", names := ns, values := vs, location := loc} : Event)
  match t with
  | .jump b => return (w, {s with block := b, position := 0}, event "jump" [] [])
  | .branch t y n =>
    let v ← eval c r e s.locals t
    let b ← boolean v
    return (w, {s with block := if b then y else n, position := 0}, event "branch" [] [v])
  | .matchResult v arms =>
    let value ← need "result unavailable" (lookup s.locals v)
    match value with
    | .result _ _ tag payload =>
      match arms.find? (·.tag == tag) with
      | none => return (w, {s with status := .unhandled tag}, event "unhandled" [v, tag] [])
      | some arm =>
        let locals ← bindPayload s.locals payload arm.bindings
        return (w, {s with block := arm.target, position := 0, locals}, event "match" [tag] [])
    | _ => .error (.stuck "match not result")
  | .stop reason => return (w, {s with status := .stopped}, event "stop" [reason] [])
  | .reject ts reason =>
    let cleaned := if e.interpretation == "edhoc_method0_suite0_v1" then {s with locals := [], slots := [], pending := none} else s
    return (w, {cleaned with status := .rejected, targets := ts.foldl (fun m t => put m t "rejected") s.targets}, event "reject" (reason :: ts) [])

def findBlock (m : Model) (s : Session) : Eval Block := do
  let role ← need ("unknown role: " ++ s.role) (m.roles.find? (·.id == s.role))
  need ("unknown block: " ++ s.block) (role.blocks.find? (·.id == s.block))
def waiting (m : Model) (s : Session) : Bool :=
  s.status == .active && s.pending.isNone && match findBlock m s with
  | .ok b => match b.steps[s.position]? with | some (_, .receive _) => true | _ => false
  | _ => false

def localStep (c : Contract) (m : Model) (e : Environment) (sid : String) (w : World) : Eval (Option World) := do
  let s ← need "unknown session" (lookup w.sessions sid)
  if s.status != .active || waiting m s then return none
  let b ← findBlock m s
  let (loc, result) := match b.steps[s.position]? with
    | some (loc, i) => (loc, instruction c m.registry e sid loc w {s with position := s.position + 1} i)
    | none => (b.endLocation, terminator c m.registry e sid b.endLocation w s b.ending)
  match result with
  | .ok (w', s', ev) => return some (appendEvent (updateSession w' sid s') ev)
  | .error fault =>
    let (status, kind, reason) := match fault with
      | .hole h => (Status.blocked h, "blocked_source", "source_hole:" ++ h)
      | .stuck r => (Status.stuck r, "stuck", r)
    return some (appendEvent (updateSession w sid {s with status})
      {session := some sid, role := s.role, kind, visibility := "analysis", names := [reason], location := loc})
end VAKE.Source
