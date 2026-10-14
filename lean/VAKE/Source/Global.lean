import VAKE.Source.Semantics
import VAKE.Network
namespace VAKE.Source
inductive Action where
  | advance (session : String)
  | spawn (session role party : String) (parameters : List (String × Network.Recipe))
  | deliver (session : String) (message : Network.Recipe)
  | remember (name : String) (value : Network.Recipe)
  | revealExport (session target : String)
  | revealState (session : String)
  | corrupt (party : String)
  deriving Repr, BEq, Inhabited

def action (c : Contract) (m : Model) (e : Environment) (w : World) (a : Action) : Eval (World × Network.RecipeState) := do
  let start : Network.RecipeState := ⟨w.counter, [], []⟩
  match a with
  | .advance sid => return ((← localStep c m e sid w).getD w, start)
  | .spawn sid role party params =>
    let rd ← need ("unknown role: " ++ role) (m.roles.find? (·.id == role))
    let (ps, rs) ← Network.parameters c m.registry e w start params
    let w' ← Network.spawn m.registry e sid role party rd.entry rd.parameters ps (Network.applyRecipe w rs)
    return (w', rs)
  | .deliver sid t =>
    let (v, rs) ← Network.recipe c m.registry e w false start t
    let s ← need "unknown session" (lookup w.sessions sid)
    let w' ← Network.deliver m.registry e sid v (waiting m s) (Network.applyRecipe w rs)
    return (w', rs)
  | .remember name t =>
    let (v, rs) ← Network.recipe c m.registry e w false start t
    return (← Network.remember name v (Network.applyRecipe w rs), rs)
  | .revealExport sid target => return (← Network.expose m.registry e "reveal_export" sid target w, start)
  | .revealState sid => return (← Network.expose m.registry e "reveal_state" sid "" w, start)
  | .corrupt p => return (← Network.expose m.registry e "corrupt" p "" w, start)

def commits (c : Contract) (m : Model) (e : Environment) (w : World) (a : Action) (next : World) : Prop :=
  match a with
  | .advance sid => localStep c m e sid w = .ok (some next)
  | _ => True

inductive Step (c : Contract) (m : Model) (e : Environment) : Configuration → Action → List Event → Configuration → Prop where
  | commit {s w a rs} (execution : action c m e s.world a = .ok (w, rs))
      (committed : commits c m e s.world a w)
      (knowledge : Network.admitted c m.registry e s.world rs) :
      Step c m e s a (w.history.drop s.world.history.length) ⟨w⟩
inductive Trace (c : Contract) (m : Model) (e : Environment) : Configuration → List Action → List Event → Configuration → Prop where
  | nil (s) : Trace c m e s [] [] s
  | cons {s u t a as ls rest} : Step c m e s a ls u → Trace c m e u as rest t → Trace c m e s (a :: as) (ls ++ rest) t

inductive Run (c : Contract) (m : Model) (e : Environment) (sid : String) : World → List Event → World → Prop where
  | done {w} : localStep c m e sid w = .ok none → Run c m e sid w [] w
  | more {w u t ls} : localStep c m e sid w = .ok (some u) → Run c m e sid u ls t →
      Run c m e sid w (u.history.drop w.history.length ++ ls) t
end VAKE.Source
