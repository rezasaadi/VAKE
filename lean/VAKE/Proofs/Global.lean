import VAKE.Proofs.Local
import VAKE.Source.Global
import VAKE.Target.Global
namespace VAKE.Translate
def action : Source.Action → Target.Action
  | .advance s => .tick s
  | .spawn s r p ps => .create s r p ps
  | .deliver s v => .inject s v
  | .remember n v => .compute n v
  | .revealExport s t => .exposeOutput s t
  | .revealState s => .exposeMemory s
  | .corrupt p => .compromise p
end VAKE.Translate
namespace VAKE.Proofs
@[simp] theorem value_id : Translate.value = id := rfl
@[simp] theorem label_id : Translate.label = id := rfl

theorem deduction (c : Contract) (m : Source.Model) (e : Environment) (roots : List Val) (v : Val)
    (h : Network.Deducible c m.registry e roots v) :
    Network.Deducible c (Translate.model m).registry (Translate.environment e) (roots.map Translate.value) (Translate.value v) := by
  simpa [Translate.model, Translate.environment, value_id] using h

theorem action (c : Contract) (m : Source.Model) (e : Environment) (w : World) (a : Source.Action) :
    Target.action c (Translate.model m) e w (Translate.action a) = Source.action c m e w a := by
  cases a with
  | advance => simp [Translate.action, Target.action, Source.action, localStep]
  | spawn sid role party params =>
    simp only [Translate.action, Target.action, Source.action, Translate.model, role_find]
    cases m.roles.find? (·.id == role) <;> rfl
  | deliver sid recipe =>
    simp only [Translate.action, Target.action, Source.action, Translate.model]
    cases Network.recipe c m.registry e w false ⟨w.counter, [], []⟩ recipe with
    | error => rfl
    | ok pair =>
      rcases pair with ⟨v, rs⟩
      simp only [Except.bind, Bind.bind]
      cases need "unknown session" (lookup w.sessions sid) with
      | error => rfl
      | ok s =>
        have hw := waiting m s
        unfold Translate.model at hw
        simp [hw]
  | remember => rfl
  | revealExport => rfl
  | revealState => rfl
  | corrupt => rfl

theorem commitment (c : Contract) (m : Source.Model) (e : Environment)
    (w next : World) (a : Source.Action) :
    Target.commits c (Translate.model m) e w (Translate.action a) next = Source.commits c m e w a next := by
  cases a <;> simp [Target.commits, Source.commits, Translate.action, localStep]

theorem step_preservation (c : Contract) (m : Source.Model) (e : Environment)
    {s s' : Source.Configuration} {a : Source.Action} {labels : List Event}
    (h : Source.Step c m e s a labels s') {t : Target.Configuration} (related : Translate.Related s t) :
    ∃ t', Target.Step c (Translate.model m) (Translate.environment e) t (Translate.action a)
      (labels.map Translate.label) t' ∧ Translate.Related s' t' := by
  cases t with | mk tw =>
    change tw = s.world at related
    subst tw
    cases h with
    | commit execution committed knowledge =>
      refine ⟨⟨_⟩, ?_, rfl⟩
      simp only [label_id, List.map_id, Translate.environment]
      apply Target.Step.commit
      · rw [action]; exact execution
      · rw [commitment]; exact committed
      · exact knowledge

theorem step_reflection (c : Contract) (m : Source.Model) (e : Environment)
    {s : Source.Configuration} {a : Source.Action} {labels : List Event} {t' : Target.Configuration}
    (h : Target.Step c (Translate.model m) e (Translate.configuration s) (Translate.action a) labels t') :
    ∃ s', Source.Step c m e s a labels s' ∧ Translate.Related s' t' := by
  cases h with
  | commit execution committed knowledge =>
    refine ⟨⟨_⟩, ?_, rfl⟩
    apply Source.Step.commit
    · rw [action] at execution; exact execution
    · rw [commitment] at committed; exact committed
    · exact knowledge

theorem finite_trace_preservation (c : Contract) (m : Source.Model) (e : Environment)
    {s s' : Source.Configuration} {as : List Source.Action} {labels : List Event}
    (h : Source.Trace c m e s as labels s') :
    Target.Trace c (Translate.model m) e (Translate.configuration s) (as.map Translate.action)
      labels (Translate.configuration s') := by
  induction h with
  | nil => exact .nil _
  | @cons s u t a as ls rest step trace ih =>
    apply Target.Trace.cons (u := Translate.configuration u)
    · cases step with
      | commit execution committed knowledge =>
        apply Target.Step.commit
        · rw [action]; exact execution
        · rw [commitment]; exact committed
        · exact knowledge
    · exact ih

theorem finite_trace_reflection (c : Contract) (m : Source.Model) (e : Environment)
    (as : List Source.Action) (s : Source.Configuration) (labels : List Event) (t : Target.Configuration)
    (h : Target.Trace c (Translate.model m) e (Translate.configuration s) (as.map Translate.action) labels t) :
    ∃ s', Source.Trace c m e s as labels s' ∧ Translate.Related s' t := by
  induction as generalizing s labels t with
  | nil => cases h; exact ⟨s, .nil s, rfl⟩
  | cons a as ih =>
    cases h with
    | cons step trace =>
      obtain ⟨u, hs, hu⟩ := step_reflection c m e step
      cases u with | mk uw =>
        rename_i ut _ _
        cases ut with | mk tw =>
          change tw = uw at hu
          subst tw
          obtain ⟨last, ht, hr⟩ := ih ⟨uw⟩ _ _ trace
          exact ⟨last, .cons hs ht, hr⟩

theorem run_preservation (c : Contract) (m : Source.Model) (e : Environment) (sid : String)
    {w u : World} {labels : List Event} (h : Source.Run c m e sid w labels u) :
    Target.Run c (Translate.model m) e sid w labels u := by
  induction h with
  | done eq => exact .done (by rw [localStep]; exact eq)
  | more eq _ ih => exact .more (by rw [localStep]; exact eq) ih

theorem run_normalization (c : Contract) (m : Source.Model) (e : Environment) (sid : String)
    {w u : World} {labels : List Event} (h : Source.Run c m e sid w labels u) :
    ∃ n, Source.Trace c m e ⟨w⟩ (List.replicate n (.advance sid)) labels ⟨u⟩ := by
  induction h with
  | done eq => exact ⟨0, .nil _⟩
  | @more w u t ls eq rest ih =>
    obtain ⟨n, ht⟩ := ih
    refine ⟨n + 1, ?_⟩
    apply Source.Trace.cons (u := ⟨u⟩) (as := List.replicate n (.advance sid))
    · apply Source.Step.commit (rs := ⟨w.counter, [], []⟩)
      · simp only [Source.action, eq]; rfl
      · exact eq
      · simp [Network.admitted]
    · exact ht

theorem run_reflection (c : Contract) (m : Source.Model) (e : Environment) (sid : String)
    {w u : World} {labels : List Event} (h : Target.Run c (Translate.model m) e sid w labels u) :
    Source.Run c m e sid w labels u := by
  induction h with
  | done eq => exact .done (by rw [localStep] at eq; exact eq)
  | more eq _ ih => exact .more (by rw [localStep] at eq; exact eq) ih

theorem histories {s : Source.Configuration} {t : Target.Configuration} (h : Translate.Related s t) :
    t.state.history = s.world.history := congrArg World.history h
theorem terminal_outcomes {s : Source.Configuration} {t : Target.Configuration} (h : Translate.Related s t) :
    t.state.sessions = s.world.sessions := congrArg World.sessions h
theorem accept_export_events {s : Source.Configuration} {t : Target.Configuration} (h : Translate.Related s t) :
    (t.state.history.filter (fun ev => ev.kind == "accept" || ev.kind == "export")) =
    (s.world.history.filter (fun ev => ev.kind == "accept" || ev.kind == "export")) := by rw [histories h]
theorem context_fields (c : Contract) (r : Registry) (e : Environment) (l : Store) (ctx : Source.Context) :
    Target.evaluate c r e l (Translate.context ctx).expression = Source.eval c r e l ctx.recipe := term c r e l ctx.recipe
end VAKE.Proofs
