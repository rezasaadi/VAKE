import VAKE.Target.Semantics
import VAKE.Network
namespace VAKE.Target
inductive Action where
  | tick (session : String)
  | create (session process party : String) (parameters : List (String × Network.Recipe))
  | inject (session : String) (message : Network.Recipe)
  | compute (name : String) (value : Network.Recipe)
  | exposeOutput (session target : String)
  | exposeMemory (session : String)
  | compromise (party : String)
  deriving Repr, BEq, Inhabited

def action (c : Contract) (p : Program) (e : Environment) (w : World) (a : Action) : Eval (World × Network.RecipeState) := do
  let start : Network.RecipeState := ⟨w.counter, [], []⟩
  match a with
  | .tick sid => return ((← step c p e sid w).getD w, start)
  | .create sid process party params =>
    let pd ← need ("unknown role: " ++ process) (p.processes.find? (·.id == process))
    let (ps, rs) ← Network.parameters c p.registry e w start params
    let w' ← Network.spawn p.registry e sid process party pd.entry pd.parameters ps (Network.applyRecipe w rs)
    return (w', rs)
  | .inject sid t =>
    let (v, rs) ← Network.recipe c p.registry e w false start t
    let s ← need "unknown session" (lookup w.sessions sid)
    let w' ← Network.deliver p.registry e sid v (waiting p s) (Network.applyRecipe w rs)
    return (w', rs)
  | .compute name t =>
    let (v, rs) ← Network.recipe c p.registry e w false start t
    return (← Network.remember name v (Network.applyRecipe w rs), rs)
  | .exposeOutput sid target => return (← Network.expose p.registry e "reveal_export" sid target w, start)
  | .exposeMemory sid => return (← Network.expose p.registry e "reveal_state" sid "" w, start)
  | .compromise party => return (← Network.expose p.registry e "corrupt" party "" w, start)

def commits (c : Contract) (p : Program) (e : Environment) (w : World) (a : Action) (next : World) : Prop :=
  match a with
  | .tick sid => step c p e sid w = .ok (some next)
  | _ => True

inductive Step (c : Contract) (p : Program) (e : Environment) : Configuration → Action → List Event → Configuration → Prop where
  | commit {t w a rs} (execution : action c p e t.state a = .ok (w, rs))
      (committed : commits c p e t.state a w)
      (knowledge : Network.admitted c p.registry e t.state rs) :
      Step c p e t a (w.history.drop t.state.history.length) ⟨w⟩
inductive Trace (c : Contract) (p : Program) (e : Environment) : Configuration → List Action → List Event → Configuration → Prop where
  | nil (t) : Trace c p e t [] [] t
  | cons {s u t a as ls rest} : Step c p e s a ls u → Trace c p e u as rest t → Trace c p e s (a :: as) (ls ++ rest) t
inductive Run (c : Contract) (p : Program) (e : Environment) (sid : String) : World → List Event → World → Prop where
  | done {w} : step c p e sid w = .ok none → Run c p e sid w [] w
  | more {w u t ls} : step c p e sid w = .ok (some u) → Run c p e sid u ls t →
      Run c p e sid w (u.history.drop w.history.length ++ ls) t
end VAKE.Target
