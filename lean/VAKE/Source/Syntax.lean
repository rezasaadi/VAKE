import VAKE.Common
namespace VAKE.Source
mutual
  inductive Term where
    | ref (id : String)
    | literal (ty json : String)
    | record (constructor : String) (fields : Fields)
    | project (record : Term) (field : String)
    | encode (encoding : String) (record : Term)
    | apply (primitive : String) (args : Args)
    | hole (id ty : String)
    deriving Repr, BEq, Inhabited
  inductive Args where
    | nil
    | cons (term : Term) (rest : Args)
    deriving Repr, BEq, Inhabited
  inductive Fields where
    | nil
    | cons (name : String) (term : Term) (rest : Fields)
    deriving Repr, BEq, Inhabited
end
inductive Instruction where
  | assign (output : String) (term : Term)
  | sample (output generator : String)
  | invoke (primitive : String) (args : Args) (output : String)
  | receive (output : String)
  | send (bytes : Term) (channel : String)
  | read (slot output : String)
  | write (slot : String) (value : Term)
  | erase (object : String)
  | emit (name : String) (args : Args) (visibility : String)
  | accept (target : String) (key : Term) (peer : Option Term)
  | exportKey (target : String) (key : Term)
  deriving Repr, BEq, Inhabited
structure Arm where
  tag : String
  bindings : List (String × String)
  target : String
  deriving Repr, BEq, Inhabited
inductive Terminator where
  | jump (block : String)
  | branch (condition : Term) (yes no : String)
  | matchResult (result : String) (arms : List Arm)
  | stop (reason : String)
  | reject (targets : List String) (reason : String)
  deriving Repr, BEq, Inhabited
structure Block where
  id : String
  steps : List (String × Instruction)
  endLocation : String
  ending : Terminator
  deriving Repr, BEq, Inhabited
structure Role where
  id : String
  parameters : List String
  entry : String
  blocks : List Block
  deriving Repr, BEq, Inhabited
structure Context where
  id : String
  role : String
  stage : String
  purpose : String
  recipe : Term
  deriving Repr, BEq, Inhabited
structure Model where
  protocol : String
  registry : Registry
  roles : List Role
  contexts : List Context
  messages : List (String × String × String × String × String)
  holes : List (String × String × String × String × List String)
  deriving Repr, BEq, Inhabited
structure Configuration where
  world : World
  deriving Repr, BEq, Inhabited
end VAKE.Source
