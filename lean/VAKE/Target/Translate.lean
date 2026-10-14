import VAKE.Source.Syntax
import VAKE.Target.Syntax
namespace VAKE.Translate
mutual
  def term : Source.Term → Target.Expr
    | .ref v => .load v
    | .literal t j => .constant t j
    | .record c f => .build c (fields f)
    | .project t f => .select (term t) f
    | .encode e t => .serialize e (term t)
    | .apply p a => .call p (args a)
    | .hole h t => .unavailable h t
  def args : Source.Args → Target.Operands
    | .nil => .nil
    | .cons t ts => .cons (term t) (args ts)
  def fields : Source.Fields → Target.Members
    | .nil => .nil
    | .cons n t ts => .cons n (term t) (fields ts)
end
def instruction : Source.Instruction → Target.Code
  | .assign o t => .store o (term t)
  | .sample o g => .generate o g
  | .invoke p a o => .execute p (args a) o
  | .receive o => .input o
  | .send t c => .publish (term t) c
  | .read s o => .fetch s o
  | .write s t => .update s (term t)
  | .erase o => .clear o
  | .emit n a v => .log n (args a) v
  | .accept t k p => .commit t (term k) (p.map term)
  | .exportKey t k => .output t (term k)
def arm (a : Source.Arm) : Target.Edge := ⟨a.tag, a.bindings, a.target⟩
def terminator : Source.Terminator → Target.Control
  | .jump b => .goto b
  | .branch c y n => .choose (term c) y n
  | .matchResult r arms => .dispatch r (arms.map arm)
  | .stop r => .halt r
  | .reject ts r => .refuse ts r
def block (b : Source.Block) : Target.Segment :=
  ⟨b.id, b.steps.map (fun (l, i) => (l, instruction i)), b.endLocation, terminator b.ending⟩
def role (r : Source.Role) : Target.Process := ⟨r.id, r.parameters, r.entry, r.blocks.map block⟩
def context (c : Source.Context) : Target.Context := ⟨c.id, c.role, c.stage, c.purpose, term c.recipe⟩
def model (m : Source.Model) : Target.Program :=
  ⟨m.protocol, m.registry, m.roles.map role, m.contexts.map context, m.messages, m.holes⟩
def configuration (s : Source.Configuration) : Target.Configuration := ⟨s.world⟩
def environment (e : Environment) : Environment := e
def value (v : Val) : Val := v
def label (e : Event) : Event := e
def Related (s : Source.Configuration) (t : Target.Configuration) : Prop := t.state = s.world
end VAKE.Translate
