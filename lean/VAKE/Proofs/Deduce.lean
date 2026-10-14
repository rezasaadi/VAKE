import VAKE.Network

namespace VAKE.Network

theorem ded_encoded {c : Contract} {r : Registry} {e : Environment} {roots : List Val}
    {id : String} {x : Val}
    (h : Deducible c r e roots x) (he : c.encode r id x = .ok (.encoded id x)) :
    Deducible c r e roots (.encoded id x) := .encode id x _ h he

theorem ded_record {c : Contract} {r : Registry} {e : Environment} {roots : List Val}
    {ty ctor : String} {fs : List (String × Val)}
    (hf : ∀ n x, (n, x) ∈ fs → Deducible c r e roots x)
    (he : c.record r ctor fs = .ok (.record ty ctor fs)) :
    Deducible c r e roots (.record ty ctor fs) := .record ctor fs _ hf he

theorem ded_fields_nil {c : Contract} {r : Registry} {e : Environment} {roots : List Val} :
    ∀ n x, (n, x) ∈ ([] : List (String × Val)) → Deducible c r e roots x := by
  intro n x h; cases h

theorem ded_fields_cons {c : Contract} {r : Registry} {e : Environment} {roots : List Val}
    {m : String} {y : Val} {fs : List (String × Val)}
    (h : Deducible c r e roots y) (rest : ∀ n x, (n, x) ∈ fs → Deducible c r e roots x) :
    ∀ n x, (n, x) ∈ (m, y) :: fs → Deducible c r e roots x := by
  intro n x hx
  cases hx with
  | head => exact h
  | tail _ hx => exact rest n x hx

def unwrap : Val → Val
  | .encoded _ v => v
  | v => v

theorem ded_unwrap_root {c : Contract} {r : Registry} {e : Environment} {roots : List Val} {u : Val}
    (h : u ∈ roots) : Deducible c r e roots (unwrap u) := by
  cases u with
  | encoded id v => exact .decode id v (.root _ h)
  | _ => exact .root _ h

theorem ded_decode_root {c : Contract} {r : Registry} {e : Environment} {roots : List Val} {out : Val}
    (h : ∃ u, u ∈ roots ∧ unwrap u = out) : Deducible c r e roots out := by
  obtain ⟨u, hu, rfl⟩ := h
  exact ded_unwrap_root hu

def fieldsOf : Val → List (String × Val)
  | .record _ _ fs => fs
  | .result _ _ _ fs => fs
  | _ => []

theorem ded_project_root {c : Contract} {r : Registry} {e : Environment} {roots : List Val} {out : Val}
    (h : ∃ u, u ∈ roots ∧ ∃ p, p ∈ fieldsOf (unwrap u) ∧ c.project (unwrap u) p.1 = .ok out) :
    Deducible c r e roots out := by
  obtain ⟨u, hu, p, _, hp⟩ := h
  exact .project _ p.1 out (ded_unwrap_root hu) hp

theorem exists_mem_tail {α : Type} {P : α → Prop} {a : α} {l : List α}
    (h : ∃ v, v ∈ l ∧ P v) : ∃ v, v ∈ a :: l ∧ P v := by
  obtain ⟨v, hv, hp⟩ := h
  exact ⟨v, List.mem_cons_of_mem a hv, hp⟩

theorem required_nil {c : Contract} {r : Registry} {e : Environment} {known : List Val} :
    ∀ extra v, (extra, v) ∈ ([] : List (List Val × Val)) → Deducible c r e (known ++ extra) v := by
  intro extra v h; cases h

theorem required_cons {c : Contract} {r : Registry} {e : Environment} {known : List Val}
    {x : List Val} {y : Val} {rest : List (List Val × Val)}
    (h : Deducible c r e (known ++ x) y)
    (tail : ∀ extra v, (extra, v) ∈ rest → Deducible c r e (known ++ extra) v) :
    ∀ extra v, (extra, v) ∈ (x, y) :: rest → Deducible c r e (known ++ extra) v := by
  intro extra v hv
  cases hv with
  | head => exact h
  | tail _ hv => exact tail extra v hv

syntax "mem_search" : tactic
macro_rules
  | `(tactic| mem_search) => `(tactic| first
      | exact List.mem_cons_self ..
      | (refine List.mem_cons_of_mem _ ?_; mem_search))

syntax "exists_search" : tactic
macro_rules
  | `(tactic| exists_search) => `(tactic| first
      | exact ⟨_, List.mem_cons_self .., by rfl⟩
      | (refine exists_mem_tail ?_; exists_search))

syntax "root_field_search" : tactic
macro_rules
  | `(tactic| root_field_search) => `(tactic| first
      | (refine ⟨_, List.mem_cons_self .., ?_⟩; exists_search)
      | (refine exists_mem_tail ?_; root_field_search))

syntax "deduce" : tactic
syntax "fields_search" : tactic
macro_rules
  | `(tactic| deduce) => `(tactic| first
      | (refine Deducible.root _ ?_; mem_search)
      | exact Deducible.atom _ _ _ (by rfl)
      | (refine ded_encoded ?_ (by rfl); deduce)
      | (refine ded_record ?_ (by rfl); fields_search)
      | (refine ded_decode_root ?_; exists_search)
      | (refine ded_project_root ?_; root_field_search)
      | exact Deducible.literal _ _ _ (by rfl))
macro_rules
  | `(tactic| fields_search) => `(tactic| first
      | exact ded_fields_nil
      | (refine ded_fields_cons (by deduce) ?_; fields_search))

syntax "admitted_search" : tactic
syntax "required_search" : tactic
macro_rules
  | `(tactic| required_search) => `(tactic| first
      | exact required_nil
      | (refine required_cons (by deduce) ?_; required_search))
macro_rules
  | `(tactic| admitted_search) => `(tactic| (unfold Network.admitted; required_search))

end VAKE.Network
