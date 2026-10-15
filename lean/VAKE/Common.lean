import Lean.Data.Json

namespace VAKE

inductive Val where
  | literal (ty : String) (json : String)
  | atom (ty name origin : String) (length : Option Nat)
  | record (ty constructor : String) (fields : List (String × Val))
  | encoded (encoding : String) (record : Val)
  | app (ty op : String) (args : List Val)
  | result (ty primitive tag : String) (payload : List (String × Val))
  deriving Repr, BEq, Inhabited

def Val.typeId : Val → String
  | .literal t _ | .atom t _ _ _ | .record t _ _ | .app t _ _ | .result t _ _ _ => t
  | .encoded .. => "Bytes"

def Val.str (s : String) : String := toString s.length ++ ":" ++ s
mutual
def Val.key : Val → String
  | .literal t j => "L" ++ Val.str t ++ Val.str j
  | .atom t n o l => "A" ++ Val.str t ++ Val.str n ++ Val.str o ++
      (match l with | none => "N" | some k => "S" ++ Val.str (toString k))
  | .record t c fs => "R" ++ Val.str t ++ Val.str c ++ "[" ++ Val.fieldKeys fs ++ "]"
  | .encoded i v => "E" ++ Val.str i ++ Val.key v
  | .app t o as => "P" ++ Val.str t ++ Val.str o ++ "[" ++ Val.listKeys as ++ "]"
  | .result t p g fs => "Q" ++ Val.str t ++ Val.str p ++ Val.str g ++ "[" ++ Val.fieldKeys fs ++ "]"
def Val.listKeys : List Val → String
  | [] => ""
  | v :: vs => Val.key v ++ Val.listKeys vs
def Val.fieldKeys : List (String × Val) → String
  | [] => ""
  | (n, v) :: fs => Val.str n ++ Val.key v ++ Val.fieldKeys fs
end

instance (priority := high) instBEqValKey : BEq Val := ⟨fun a b => a.key == b.key⟩

def Val.insertSorted (x : Val) : List Val → List Val
  | [] => [x]
  | y :: ys => if decide (x.key ≤ y.key) then x :: y :: ys else y :: Val.insertSorted x ys

def Val.sort : List Val → List Val
  | [] => []
  | x :: xs => Val.insertSorted x (Val.sort xs)

abbrev Store := List (String × Val)
def lookup (xs : List (String × α)) (key : String) : Option α := (xs.find? (·.1 == key)).map Prod.snd
def put (xs : List (String × α)) (key : String) (v : α) : List (String × α) :=
  (key, v) :: xs.filter (·.1 != key)
def remove (xs : List (String × α)) (key : String) : List (String × α) := xs.filter (·.1 != key)

structure TypeDecl where
  id : String
  kind : String
  parameters : List String
  fields : List (String × String)
  primitive : Option String
  deriving Repr, BEq, Inhabited
structure Primitive where
  id : String
  family : String
  mode : String
  op : String
  failure : String
  inputs : List (String × String × String)
  outcomes : List (String × List (String × String))
  laws : List String
  deriving Repr, BEq, Inhabited
structure Constructor where
  id : String
  ty : String
  fields : List (String × String)
  deriving Repr, BEq, Inhabited
structure Encoding where
  id : String
  family : String
  types : List String
  laws : List String
  deriving Repr, BEq, Inhabited
structure ValueDecl where
  id : String
  ty : String
  owner : String
  storage : String
  deriving Repr, BEq, Inhabited
structure Slot where
  id : String
  ty : String
  scope : String
  policy : String
  deriving Repr, BEq, Inhabited
structure TargetDecl where
  id : String
  role : String
  stage : String
  ty : String
  peerMode : String
  outputKind : String
  properties : List String
  partnering : String
  exposure : String
  deriving Repr, BEq, Inhabited
structure Registry where
  types : List TypeDecl
  primitives : List Primitive
  constructors : List Constructor
  encodings : List Encoding
  values : List ValueDecl
  slots : List Slot
  targets : List TargetDecl
  deriving Repr, BEq, Inhabited

inductive Fault where
  | hole (id : String)
  | stuck (reason : String)
  deriving Repr, BEq, Inhabited
abbrev Eval := Except Fault
def need (msg : String) : Option α → Eval α
  | some x => .ok x
  | none => .error (.stuck msg)

structure Credential where
  domain : String
  reference : String
  principal : String
  keyOwner : String
  deriving Repr, BEq, Inhabited

structure Environment where
  interpretation : String
  phase : String
  exposures : List String
  parties : List String
  credentials : List Credential
  kemCorrectness : String
  correctnessErrorSessions : List String
  deriving Repr, BEq, Inhabited


structure Contract where
  literal : Registry → String → String → Eval Val
  record : Registry → String → List (String × Val) → Eval Val
  project : Val → String → Eval Val
  encode : Registry → String → Val → Eval Val
  pure : Registry → Environment → String → List Val → Eval Val
  invoke : Registry → Environment → String → String → List Val → Nat →
    Eval (String × List (String × Val) × Nat)

inductive Status where
  | active | stopped | rejected | blocked (hole : String) | unhandled (tag : String) | stuck (reason : String)
  deriving Repr, BEq, Inhabited
structure Session where
  role : String
  party : String
  block : String
  position : Nat := 0
  status : Status := .active
  locals : Store := []
  slots : Store := []
  targets : List (String × String) := []
  pending : Option Val := none
  deriving Repr, BEq, Inhabited

structure Event where
  session : Option String
  role : String := ""
  kind : String
  visibility : String
  names : List String := []
  values : List Val := []
  location : String := ""
  deriving Repr, BEq, Inhabited
structure World where
  sessions : List (String × Session) := []
  persistent : List (String × Store) := []
  counter : Nat := 0
  history : List Event := []
  knowledge : List Val := []
  sent : List Val := []
  names : Store := []
  deriving Repr, BEq, Inhabited

def appendEvent (w : World) (e : Event) : World := { w with history := w.history ++ [e] }
def updateSession (w : World) (sid : String) (s : Session) : World :=
  { w with sessions := put w.sessions sid s }
def readSlot (r : Registry) (w : World) (s : Session) (id : String) : Eval Val := do
  let slot ← need ("unknown slot: " ++ id) (r.slots.find? (·.id == id))
  need ("unset slot: " ++ id) (lookup (if slot.scope == "party_persistent" then
    (lookup w.persistent s.party).getD [] else s.slots) id)
def writeSlot (r : Registry) (w : World) (s : Session) (id : String) (v : Val) : Eval (World × Session) := do
  let slot ← need ("unknown slot: " ++ id) (r.slots.find? (·.id == id))
  if slot.scope == "party_persistent" then
    return ({w with persistent := put w.persistent s.party (put ((lookup w.persistent s.party).getD []) id v)}, s)
  else return (w, {s with slots := put s.slots id v})
def eraseObject (r : Registry) (w : World) (s : Session) (id : String) : World × Session :=
  match r.slots.find? (·.id == id) with
  | some slot => if slot.scope == "party_persistent" then
      ({w with persistent := put w.persistent s.party (remove ((lookup w.persistent s.party).getD []) id)}, s)
    else (w, {s with slots := remove s.slots id})
  | none => (w, {s with locals := remove s.locals id})
def boolean : Val → Eval Bool
  | .literal "Bool" "true" => .ok true
  | .literal "Bool" "false" => .ok false
  | _ => .error (.stuck "not a Boolean")
def targetAllowed (s : Session) (target : String) : Eval Unit :=
  if lookup s.targets target == some "rejected" then .error (.stuck "target rejected") else .ok ()

end VAKE
