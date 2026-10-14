import VAKE.Symbolic

namespace VAKE.Normalization

def collidingA : Val := .atom "DhSecret" "dh_keygen:1" "session:I,adversary" (some 32)
def collidingB : Val := .atom "DhSecret" "dh_keygen:1,session:I" "adversary" (some 32)

theorem colliding_keys_differ : collidingA.key ≠ collidingB.key := by decide

theorem colliding_order_left : Symbolic.ordered [collidingA, collidingB] = [collidingA, collidingB] := by rfl
theorem colliding_order_right : Symbolic.ordered [collidingB, collidingA] = [collidingA, collidingB] := by rfl
theorem colliding_order_commutes :
    Symbolic.ordered [collidingA, collidingB] = Symbolic.ordered [collidingB, collidingA] := by
  rw [colliding_order_left, colliding_order_right]

theorem absent_and_zero_length_differ :
    (Val.atom "Nonce" "n" "o" none).key ≠ (Val.atom "Nonce" "n" "o" (some 0)).key := by decide

end VAKE.Normalization
