import VAKE.Source.Global
import VAKE.Target.Global

namespace VAKE.Commitment

theorem source_no_commit_of_none (c : Contract) (m : Source.Model) (e : Environment)
    (sid : String) (w : World) (h : Source.localStep c m e sid w = .ok none)
    (labels : List Event) (next : Source.Configuration) :
    ¬ Source.Step c m e ⟨w⟩ (.advance sid) labels next := by
  intro step
  cases step with
  | commit execution committed knowledge =>
    simp [Source.commits, h] at committed

theorem target_no_commit_of_none (c : Contract) (p : Target.Program) (e : Environment)
    (sid : String) (w : World) (h : Target.step c p e sid w = .ok none)
    (labels : List Event) (next : Target.Configuration) :
    ¬ Target.Step c p e ⟨w⟩ (.tick sid) labels next := by
  intro step
  cases step with
  | commit execution committed knowledge =>
    simp [Target.commits, h] at committed

end VAKE.Commitment
