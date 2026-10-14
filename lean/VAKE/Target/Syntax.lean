import VAKE.Common
namespace VAKE.Target

mutual
  inductive Expr where
    | load (id : String)
    | constant (ty json : String)
    | build (constructor : String) (fields : Members)
    | select (record : Expr) (field : String)
    | serialize (encoding : String) (record : Expr)
    | call (primitive : String) (args : Operands)
    | unavailable (id ty : String)
    deriving Repr, BEq, Inhabited
  inductive Operands where
    | nil
    | cons (expr : Expr) (rest : Operands)
    deriving Repr, BEq, Inhabited
  inductive Members where
    | nil
    | cons (name : String) (expr : Expr) (rest : Members)
    deriving Repr, BEq, Inhabited
end
inductive Code where
  | store (output : String) (expr : Expr)
  | generate (output generator : String)
  | execute (primitive : String) (args : Operands) (output : String)
  | input (output : String)
  | publish (bytes : Expr) (channel : String)
  | fetch (slot output : String)
  | update (slot : String) (value : Expr)
  | clear (object : String)
  | log (name : String) (args : Operands) (visibility : String)
  | commit (target : String) (key : Expr) (peer : Option Expr)
  | output (target : String) (key : Expr)
  deriving Repr, BEq, Inhabited
structure Edge where
  tag : String
  bindings : List (String × String)
  target : String
  deriving Repr, BEq, Inhabited
inductive Control where
  | goto (block : String)
  | choose (condition : Expr) (yes no : String)
  | dispatch (result : String) (arms : List Edge)
  | halt (reason : String)
  | refuse (targets : List String) (reason : String)
  deriving Repr, BEq, Inhabited
structure Segment where
  id : String
  code : List (String × Code)
  endLocation : String
  control : Control
  deriving Repr, BEq, Inhabited
structure Process where
  id : String
  parameters : List String
  entry : String
  segments : List Segment
  deriving Repr, BEq, Inhabited
structure Context where
  id : String
  role : String
  stage : String
  purpose : String
  expression : Expr
  deriving Repr, BEq, Inhabited
structure Program where
  protocol : String
  registry : Registry
  processes : List Process
  contexts : List Context
  messages : List (String × String × String × String × String)
  holes : List (String × String × String × String × List String)
  deriving Repr, BEq, Inhabited
structure Configuration where
  state : World
  deriving Repr, BEq, Inhabited
end VAKE.Target
