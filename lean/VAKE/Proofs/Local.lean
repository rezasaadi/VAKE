import VAKE.Source.Semantics
import VAKE.Target.Semantics
import VAKE.Target.Translate
namespace VAKE.Proofs
mutual
  theorem term (c : Contract) (r : Registry) (e : Environment) (l : Store) (t : Source.Term) :
      Target.evaluate c r e l (Translate.term t) = Source.eval c r e l t := by
    cases t <;> simp [Translate.term, Target.evaluate, Source.eval, term, args, fields]
  theorem args (c : Contract) (r : Registry) (e : Environment) (l : Store) (a : Source.Args) :
      Target.operands c r e l (Translate.args a) = Source.evalArgs c r e l a := by
    cases a <;> simp [Translate.args, Target.operands, Source.evalArgs, term, args]
  theorem fields (c : Contract) (r : Registry) (e : Environment) (l : Store) (fs : Source.Fields) :
      Target.members c r e l (Translate.fields fs) = Source.evalFields c r e l fs := by
    cases fs <;> simp [Translate.fields, Target.members, Source.evalFields, term, fields]
end
theorem peer (c : Contract) (r : Registry) (e : Environment) (l : Store) (p : Option Source.Term) :
    Target.peer c r e l (p.map Translate.term) = Source.evalPeer c r e l p := by
  cases p <;> simp [Target.peer, Source.evalPeer, term]
theorem instruction (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (i : Source.Instruction) :
    Target.execute c r e sid loc w s (Translate.instruction i) = Source.instruction c r e sid loc w s i := by
  cases i <;> simp [Translate.instruction, Target.execute, Source.instruction, term, args, peer]
theorem bindPayload (l p : Store) (bs : List (String × String)) :
    Target.bindFields l p bs = Source.bindPayload l p bs := by
  induction bs generalizing l with
  | nil => rfl
  | cons b bs ih =>
    rcases b with ⟨n, o⟩
    simp only [Target.bindFields, Source.bindPayload]
    cases need ("payload unavailable: " ++ n) (lookup p n) <;> simp_all
theorem arm_find (arms : List Source.Arm) (tag : String) :
    ((arms.map Translate.arm).find? (·.tag == tag)) = (arms.find? (·.tag == tag)).map Translate.arm := by
  induction arms with
  | nil => rfl
  | cons a as ih => cases h : (a.tag == tag) <;> simp [List.find?, Translate.arm, ih, h]
theorem terminator (c : Contract) (r : Registry) (e : Environment) (sid loc : String)
    (w : World) (s : Session) (t : Source.Terminator) :
    Target.transfer c r e sid loc w s (Translate.terminator t) = Source.terminator c r e sid loc w s t := by
  cases t with
  | jump => rfl
  | stop => rfl
  | reject => rfl
  | branch => simp [Translate.terminator, Target.transfer, Source.terminator, term]
  | matchResult result arms =>
    simp only [Translate.terminator, Target.transfer, Source.terminator]
    cases need "result unavailable" (lookup s.locals result) with
    | error => rfl
    | ok v =>
      cases v <;> simp only [Except.bind, Bind.bind, pure, Except.pure]
      all_goals try rfl
      rename_i ty prim tag payload
      rw [arm_find]
      cases arms.find? (·.tag == tag) <;> simp [Translate.arm, bindPayload]

theorem role_find (rs : List Source.Role) (id : String) :
    (rs.map Translate.role).find? (·.id == id) = (rs.find? (·.id == id)).map Translate.role := by
  induction rs with
  | nil => rfl
  | cons r rs ih => cases h : (r.id == id) <;> simp [List.find?, Translate.role, ih, h]
theorem block_find (bs : List Source.Block) (id : String) :
    (bs.map Translate.block).find? (·.id == id) = (bs.find? (·.id == id)).map Translate.block := by
  induction bs with
  | nil => rfl
  | cons b bs ih => cases h : (b.id == id) <;> simp [List.find?, Translate.block, ih, h]
theorem findBlock (m : Source.Model) (s : Session) :
    Target.findSegment (Translate.model m) s = (Source.findBlock m s).map Translate.block := by
  simp only [Target.findSegment, Source.findBlock, Translate.model, role_find]
  cases m.roles.find? (·.id == s.role) with
  | none => rfl
  | some r =>
    simp only [Option.map, need, Except.bind, Bind.bind, Translate.role, block_find]
    cases r.blocks.find? (·.id == s.block) <;> rfl
theorem waiting (m : Source.Model) (s : Session) :
    Target.waiting (Translate.model m) s = Source.waiting m s := by
  simp only [Target.waiting, Source.waiting, findBlock]
  cases Source.findBlock m s with
  | error => rfl
  | ok b =>
    simp only [Except.map, Translate.block, List.getElem?_map]
    cases b.steps[s.position]? with
    | none => rfl
    | some pair => rcases pair with ⟨loc, i⟩; cases i <;> rfl

theorem localStep (c : Contract) (m : Source.Model) (e : Environment) (sid : String) (w : World) :
    Target.step c (Translate.model m) e sid w = Source.localStep c m e sid w := by
  simp only [Target.step, Source.localStep, waiting, findBlock]
  cases need "unknown session" (lookup w.sessions sid) with
  | error => rfl
  | ok s =>
    simp only [Except.bind, Bind.bind]
    split
    · rfl
    · cases Source.findBlock m s with
      | error => rfl
      | ok b =>
        simp only [Except.map, Translate.block, Translate.model, List.getElem?_map]
        cases b.steps[s.position]? with
        | none =>
          simp only [Option.map, terminator]
          cases Source.terminator c m.registry e sid b.endLocation w s b.ending <;> rfl
        | some pair =>
          rcases pair with ⟨loc, i⟩
          simp only [Option.map, instruction]
          cases Source.instruction c m.registry e sid loc w {s with position := s.position + 1} i <;> rfl
end VAKE.Proofs
