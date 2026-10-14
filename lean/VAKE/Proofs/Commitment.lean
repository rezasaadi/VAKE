import VAKE.Proofs.Global
import VAKE.Proofs.NoCommit

namespace VAKE.Commitment

theorem source_commit_of_some (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w next : World) (h : Source.localStep c m e sid w = .ok (some next))
    (knowledge : Network.admitted c m.registry e w ⟨w.counter, [], []⟩) :
    Source.Step c m e ⟨w⟩ (.advance sid) (next.history.drop w.history.length) ⟨next⟩ := by
  apply Source.Step.commit (rs := ⟨w.counter, [], []⟩)
  · simp only [Source.action, h]; rfl
  · exact h
  · exact knowledge

theorem target_commit_of_some (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w next : World) (h : Target.step c p e sid w = .ok (some next))
    (knowledge : Network.admitted c p.registry e w ⟨w.counter, [], []⟩) :
    Target.Step c p e ⟨w⟩ (.tick sid) (next.history.drop w.history.length) ⟨next⟩ := by
  apply Target.Step.commit (rs := ⟨w.counter, [], []⟩)
  · simp only [Target.action, h]; rfl
  · exact h
  · exact knowledge

theorem source_commit_reflects_some (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (labels : List Event) (next : Source.Configuration)
    (h : Source.Step c m e ⟨w⟩ (.advance sid) labels next) :
    Source.localStep c m e sid w = .ok (some next.world) ∧ labels = next.world.history.drop w.history.length := by
  cases h with
  | commit execution committed knowledge => exact ⟨committed, rfl⟩

theorem target_commit_reflects_some (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (labels : List Event) (next : Target.Configuration)
    (h : Target.Step c p e ⟨w⟩ (.tick sid) labels next) :
    Target.step c p e sid w = .ok (some next.state) ∧ labels = next.state.history.drop w.history.length := by
  cases h with
  | commit execution committed knowledge => exact ⟨committed, rfl⟩

theorem source_committed_iff (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (labels : List Event) (next : World) :
    Source.Step c m e ⟨w⟩ (.advance sid) labels ⟨next⟩ ↔
      Source.localStep c m e sid w = .ok (some next) ∧ labels = next.history.drop w.history.length := by
  constructor
  · exact source_commit_reflects_some c m e sid w labels ⟨next⟩
  · rintro ⟨h, rfl⟩
    exact source_commit_of_some c m e sid w next h (by simp [Network.admitted])

theorem target_committed_iff (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (labels : List Event) (next : World) :
    Target.Step c p e ⟨w⟩ (.tick sid) labels ⟨next⟩ ↔
      Target.step c p e sid w = .ok (some next) ∧ labels = next.history.drop w.history.length := by
  constructor
  · exact target_commit_reflects_some c p e sid w labels ⟨next⟩
  · rintro ⟨h, rfl⟩
    exact target_commit_of_some c p e sid w next h (by simp [Network.admitted])

theorem source_inactive_none (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (inactive : s.status ≠ .active) : Source.localStep c m e sid w = .ok none := by
  have hi : (s.status != .active) = true := by
    cases hs : s.status <;> first | exact False.elim (inactive hs) | rfl
  simp [Source.localStep, need, found, Bind.bind, Except.bind, hi, pure, Except.pure]

theorem target_inactive_none (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (inactive : s.status ≠ .active) : Target.step c p e sid w = .ok none := by
  have hi : (s.status != .active) = true := by
    cases hs : s.status <;> first | exact False.elim (inactive hs) | rfl
  simp [Target.step, need, found, Bind.bind, Except.bind, hi, pure, Except.pure]

theorem source_waiting_none (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (waiting : Source.waiting m s = true) : Source.localStep c m e sid w = .ok none := by
  simp [Source.localStep, need, found, Bind.bind, Except.bind, waiting, pure, Except.pure]

theorem target_waiting_none (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (waiting : Target.waiting p s = true) : Target.step c p e sid w = .ok none := by
  simp [Target.step, need, found, Bind.bind, Except.bind, waiting, pure, Except.pure]

theorem source_inactive_no_commit (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (inactive : s.status ≠ .active) (labels : List Event) (next : Source.Configuration) :
    ¬ Source.Step c m e ⟨w⟩ (.advance sid) labels next :=
  source_no_commit_of_none c m e sid w (source_inactive_none c m e sid w s found inactive) labels next

theorem target_inactive_no_commit (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (inactive : s.status ≠ .active) (labels : List Event) (next : Target.Configuration) :
    ¬ Target.Step c p e ⟨w⟩ (.tick sid) labels next :=
  target_no_commit_of_none c p e sid w (target_inactive_none c p e sid w s found inactive) labels next

theorem source_waiting_no_commit (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (waiting : Source.waiting m s = true) (labels : List Event) (next : Source.Configuration) :
    ¬ Source.Step c m e ⟨w⟩ (.advance sid) labels next :=
  source_no_commit_of_none c m e sid w (source_waiting_none c m e sid w s found waiting) labels next

theorem target_waiting_no_commit (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (s : Session) (found : lookup w.sessions sid = some s)
    (waiting : Target.waiting p s = true) (labels : List Event) (next : Target.Configuration) :
    ¬ Target.Step c p e ⟨w⟩ (.tick sid) labels next :=
  target_no_commit_of_none c p e sid w (target_waiting_none c p e sid w s found waiting) labels next

theorem inactive_delivery_preserves_session (r : Registry) (e : Environment) (sid : String)
    (v : Val) (w next : World) (s : Session) (found : lookup w.sessions sid = some s)
    (inactive : s.status ≠ .active) (bytes : v.typeId = "Bytes")
    (delivered : Network.deliver r e sid v false w = .ok next) :
    lookup next.sessions sid = some s := by
  have hi : (s.status == .active) = false := by
    cases hs : s.status <;> first | exact False.elim (inactive hs) | rfl
  simp [Network.deliver, bytes, need, found, Bind.bind, Except.bind, hi, pure, Except.pure] at delivered
  split at delivered <;> cases delivered <;> simp [appendEvent, updateSession, lookup, put]

theorem source_no_trace_after_none (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (h : Source.localStep c m e sid w = .ok none)
    (rest : List Source.Action) (labels : List Event) (next : Source.Configuration) :
    ¬ Source.Trace c m e ⟨w⟩ (.advance sid :: rest) labels next := by
  intro trace
  cases trace with
  | cons step tail => exact source_no_commit_of_none c m e sid w h _ _ step

theorem target_no_trace_after_none (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (h : Target.step c p e sid w = .ok none)
    (rest : List Target.Action) (labels : List Event) (next : Target.Configuration) :
    ¬ Target.Trace c p e ⟨w⟩ (.tick sid :: rest) labels next := by
  intro trace
  cases trace with
  | cons step tail => exact target_no_commit_of_none c p e sid w h _ _ step

inductive Advances (advance : World → Eval (Option World)) : World → Nat → List Event → World → Prop where
  | nil (w) : Advances advance w 0 [] w
  | cons {w u t n ls} : advance w = .ok (some u) → Advances advance u n ls t →
      Advances advance w (n+1) (u.history.drop w.history.length ++ ls) t

theorem source_run_exact_expansion (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) {w u : World} {labels : List Event} (h : Source.Run c m e sid w labels u) :
    ∃ n, Advances (Source.localStep c m e sid) w n labels u ∧
      Source.Trace c m e ⟨w⟩ (List.replicate n (.advance sid)) labels ⟨u⟩ := by
  induction h with
  | done eq => exact ⟨0, .nil _, .nil _⟩
  | @more w u t ls eq rest ih =>
    obtain ⟨n, hs, ht⟩ := ih
    exact ⟨n+1, .cons eq hs, .cons (source_commit_of_some c m e sid w u eq (by simp [Network.admitted])) ht⟩

theorem target_run_exact_expansion (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) {w u : World} {labels : List Event} (h : Target.Run c p e sid w labels u) :
    ∃ n, Advances (Target.step c p e sid) w n labels u ∧
      Target.Trace c p e ⟨w⟩ (List.replicate n (.tick sid)) labels ⟨u⟩ := by
  induction h with
  | done eq => exact ⟨0, .nil _, .nil _⟩
  | @more w u t ls eq rest ih =>
    obtain ⟨n, hs, ht⟩ := ih
    exact ⟨n+1, .cons eq hs, .cons (target_commit_of_some c p e sid w u eq (by simp [Network.admitted])) ht⟩

theorem source_done_expands_zero (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (h : Source.localStep c m e sid w = .ok none) :
    Source.Run c m e sid w [] w ∧ Advances (Source.localStep c m e sid) w 0 [] w ∧
      ∀ labels next, ¬ Source.Step c m e ⟨w⟩ (.advance sid) labels next :=
  ⟨.done h, .nil _, source_no_commit_of_none c m e sid w h⟩

theorem target_done_expands_zero (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (h : Target.step c p e sid w = .ok none) :
    Target.Run c p e sid w [] w ∧ Advances (Target.step c p e sid) w 0 [] w ∧
      ∀ labels next, ¬ Target.Step c p e ⟨w⟩ (.tick sid) labels next :=
  ⟨.done h, .nil _, target_no_commit_of_none c p e sid w h⟩

end VAKE.Commitment
