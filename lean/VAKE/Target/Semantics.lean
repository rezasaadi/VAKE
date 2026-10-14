import VAKE.Target.Syntax
namespace VAKE.Target
mutual
  def evaluate (c : Contract) (r : Registry) (e : Environment) (memory : Store) : Expr → Eval Val
    | .load v => need ("unavailable value: " ++ v) (lookup memory v)
    | .constant t j => c.literal r t j
    | .build k fs => do c.record r k (← members c r e memory fs)
    | .select t f => do c.project (← evaluate c r e memory t) f
    | .serialize k t => do c.encode r k (← evaluate c r e memory t)
    | .call p a => do c.pure r e p (← operands c r e memory a)
    | .unavailable h _ => .error (.hole h)
  def operands (c : Contract) (r : Registry) (e : Environment) (memory : Store) : Operands → Eval (List Val)
    | .nil => .ok []
    | .cons t ts => do
      let v ← evaluate c r e memory t
      let vs ← operands c r e memory ts
      return v :: vs
  def members (c : Contract) (r : Registry) (e : Environment) (memory : Store) : Members → Eval Store
    | .nil => .ok []
    | .cons n t ts => do
      let v ← evaluate c r e memory t
      let vs ← members c r e memory ts
      return (n, v) :: vs
end
def peer (c : Contract) (r : Registry) (e : Environment) (l : Store) : Option Expr → Eval (List Val)
  | none => .ok []
  | some t => do return [← evaluate c r e l t]

def execute (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (code : Code) : Eval (World × Session × Event) := do
  let event := fun k v ns vs => ({session := some sid, role := s.role, kind := k, visibility := v, names := ns, values := vs, location := loc} : Event)
  match code with
  | .store o t =>
    let v ← evaluate c r e s.locals t
    return (w, {s with locals := put s.locals o v}, event "assign" "analysis" [o] [v])
  | .generate o g =>
    let (_, payload, counter) ← c.invoke r e sid g [] w.counter
    let v ← need "empty generator payload" (payload.head?.map Prod.snd)
    return ({w with counter}, {s with locals := put s.locals o v}, event "sample" "analysis" [o] [v])
  | .execute p a o =>
    let vs ← operands c r e s.locals a
    let (tag, payload, counter) ← c.invoke r e sid p vs w.counter
    let decl ← need "unknown result variable" (r.values.find? (·.id == o))
    let v := Val.result decl.ty p tag payload
    return ({w with counter}, {s with locals := put s.locals o v}, event "invoke" "analysis" [p, tag] (v :: vs))
  | .input o =>
    let v ← need "no delivery" s.pending
    return (w, {s with locals := put s.locals o v, pending := none}, event "receive" "analysis" [o] [v])
  | .publish t channel =>
    let v ← evaluate c r e s.locals t
    return ({w with knowledge := w.knowledge ++ [v], sent := w.sent ++ [v]}, s, event "send" "public" [channel] [v])
  | .fetch slot o =>
    let v ← readSlot r w s slot
    return (w, {s with locals := put s.locals o v}, event "read" "analysis" [slot] [v])
  | .update slot t =>
    let v ← evaluate c r e s.locals t
    let (w', s') ← writeSlot r w s slot v
    return (w', s', event "write" "analysis" [slot] [v])
  | .clear o =>
    let (w', s') := eraseObject r w s o
    return (w', s', event "erase" "analysis" [o] [])
  | .log n a vis =>
    let vs ← operands c r e s.locals a
    return ({w with knowledge := if vis == "public" then w.knowledge ++ vs else w.knowledge}, s,
      event "emit" vis [n] vs)
  | .commit t k p =>
    targetAllowed s t
    let key ← evaluate c r e s.locals k
    let other ← peer c r e s.locals p
    return (w, {s with targets := put s.targets t "accepted"}, event "accept" "local" [t] (key :: other))
  | .output t k =>
    targetAllowed s t
    let key ← evaluate c r e s.locals k
    return (w, s, event "export" "local" [t] [key])

def bindFields (locals payload : Store) : List (String × String) → Eval Store
  | [] => .ok locals
  | (name, output) :: rest => do
    let v ← need ("payload unavailable: " ++ name) (lookup payload name)
    bindFields (put locals output v) payload rest

def transfer (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (control : Control) : Eval (World × Session × Event) := do
  let event := fun k ns vs => ({session := some sid, role := s.role, kind := k, visibility := "analysis", names := ns, values := vs, location := loc} : Event)
  match control with
  | .goto b => return (w, {s with block := b, position := 0}, event "jump" [] [])
  | .choose t y n =>
    let v ← evaluate c r e s.locals t
    let b ← boolean v
    return (w, {s with block := if b then y else n, position := 0}, event "branch" [] [v])
  | .dispatch v arms =>
    let value ← need "result unavailable" (lookup s.locals v)
    match value with
    | .result _ _ tag payload =>
      match arms.find? (·.tag == tag) with
      | none => return (w, {s with status := .unhandled tag}, event "unhandled" [v, tag] [])
      | some edge =>
        let locals ← bindFields s.locals payload edge.bindings
        return (w, {s with block := edge.target, position := 0, locals}, event "match" [tag] [])
    | _ => .error (.stuck "match not result")
  | .halt reason => return (w, {s with status := .stopped}, event "stop" [reason] [])
  | .refuse ts reason =>
    let cleaned := if e.interpretation == "edhoc_method0_suite0_v1" then {s with locals := [], slots := [], pending := none} else s
    return (w, {cleaned with status := .rejected, targets := ts.foldl (fun m t => put m t "rejected") s.targets}, event "reject" (reason :: ts) [])

def findSegment (p : Program) (s : Session) : Eval Segment := do
  let process ← need ("unknown role: " ++ s.role) (p.processes.find? (·.id == s.role))
  need ("unknown block: " ++ s.block) (process.segments.find? (·.id == s.block))
def waiting (p : Program) (s : Session) : Bool :=
  s.status == .active && s.pending.isNone && match findSegment p s with
  | .ok b => match b.code[s.position]? with | some (_, .input _) => true | _ => false
  | _ => false

def step (c : Contract) (p : Program) (e : Environment) (sid : String) (w : World) : Eval (Option World) := do
  let s ← need "unknown session" (lookup w.sessions sid)
  if s.status != .active || waiting p s then return none
  let b ← findSegment p s
  let (loc, result) := match b.code[s.position]? with
    | some (loc, code) => (loc, execute c p.registry e sid loc w {s with position := s.position + 1} code)
    | none => (b.endLocation, transfer c p.registry e sid b.endLocation w s b.control)
  match result with
  | .ok (w', s', ev) => return some (appendEvent (updateSession w' sid s') ev)
  | .error fault =>
    let (status, kind, reason) := match fault with
      | .hole h => (Status.blocked h, "blocked_source", "source_hole:" ++ h)
      | .stuck r => (Status.stuck r, "stuck", r)
    return some (appendEvent (updateSession w sid {s with status})
      {session := some sid, role := s.role, kind, visibility := "analysis", names := [reason], location := loc})
end VAKE.Target
