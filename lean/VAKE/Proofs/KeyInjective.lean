import VAKE.Common

/-!
# Injectivity of the symbolic-equality key

`Val.key` is the length-prefixed structural serialization that VAKE uses for symbolic
equality (`BEq Val`) and for the canonical order of commutative arguments (DH, XOR).
This file proves that the serialization is prefix-free and therefore injective, so
key equality coincides with structural equality of values.
-/

namespace VAKE.KeyInjective

/-! ## Decimal length prefixes -/

/-- Left inverse of `Nat.toDigits 10` on the digits it produces. -/
def decodeDigits (cs : List Char) : Nat :=
  cs.foldl (fun acc c => acc * 10 + (c.toNat - 48)) 0

private theorem decodeDigits_append_single (cs : List Char) (c : Char) :
    decodeDigits (cs ++ [c]) = decodeDigits cs * 10 + (c.toNat - 48) := by
  simp [decodeDigits, List.foldl_append]

private theorem decodeDigits_toDigits (n : Nat) : decodeDigits (Nat.toDigits 10 n) = n := by
  induction n using Nat.strongRecOn with
  | _ n ih =>
    rw [Nat.toDigits_eq_ite (by decide)]
    split
    · rename_i h
      simp [decodeDigits, Nat.toNat_digitChar_sub_48_of_lt_ten h]
    · rename_i h
      rw [decodeDigits_append_single, ih (n / 10) (by omega),
        Nat.toNat_digitChar_sub_48_of_lt_ten (Nat.mod_lt _ (by decide))]
      omega

private theorem toDigits_inj {m n : Nat} (h : Nat.toDigits 10 m = Nat.toDigits 10 n) : m = n := by
  have := congrArg decodeDigits h
  simpa [decodeDigits_toDigits] using this

private theorem colon_not_digit_of_mem {n : Nat} {c : Char} (h : c ∈ Nat.toDigits 10 n) : c ≠ ':' := by
  intro hc
  have := Nat.isDigit_of_mem_toDigits (by decide) (by decide) h
  subst hc
  exact absurd this (by decide)

/-- Splitting at the first colon recovers the digit block. -/
private theorem split_colon : ∀ (d₁ d₂ r₁ r₂ : List Char),
    (∀ c ∈ d₁, c ≠ ':') → (∀ c ∈ d₂, c ≠ ':') →
    d₁ ++ ':' :: r₁ = d₂ ++ ':' :: r₂ → d₁ = d₂ ∧ r₁ = r₂
  | [], [], _, _, _, _, h => by simpa using h
  | [], c :: _, _, _, _, h₂, h => by
      simp only [List.nil_append, List.cons_append, List.cons.injEq] at h
      exact absurd h.1.symm (h₂ c (by simp))
  | c :: _, [], _, _, h₁, _, h => by
      simp only [List.nil_append, List.cons_append, List.cons.injEq] at h
      exact absurd h.1 (h₁ c (by simp))
  | c₁ :: d₁, c₂ :: d₂, r₁, r₂, h₁, h₂, h => by
      simp only [List.cons_append, List.cons.injEq] at h
      obtain ⟨hc, h⟩ := h
      have := split_colon d₁ d₂ r₁ r₂ (fun c hm => h₁ c (by simp [hm]))
        (fun c hm => h₂ c (by simp [hm])) h
      exact ⟨by rw [hc, this.1], this.2⟩

/-- Characters of a length-prefixed string. -/
@[irreducible] def S (s : String) : List Char := (Val.str s).toList

private theorem S_eq (s : String) : S s = Nat.toDigits 10 s.length ++ ':' :: s.toList := by
  simp [S, Val.str, String.toList_append, Nat.toString_eq_repr, Nat.toList_repr]

private theorem S_head (s : String) : ∃ c r, S s = c :: r ∧ c.isDigit = true := by
  rw [S_eq]
  match h : Nat.toDigits 10 s.length with
  | [] => exact absurd h Nat.toDigits_ne_nil
  | c :: r =>
    refine ⟨c, r ++ ':' :: s.toList, rfl, ?_⟩
    exact Nat.isDigit_of_mem_toDigits (b := 10) (n := s.length) (by decide) (by decide) (by rw [h]; simp)

/-- Length-prefixed strings are prefix-free. -/
private theorem S_prefix {x y : String} {s t : List Char} (h : S x ++ s = S y ++ t) : x = y ∧ s = t := by
  rw [S_eq, S_eq] at h
  simp only [List.append_assoc, List.cons_append] at h
  obtain ⟨hd, hr⟩ := split_colon _ _ _ _ (fun _ hm => colon_not_digit_of_mem hm)
    (fun _ hm => colon_not_digit_of_mem hm) h
  have hlen : x.toList.length = y.toList.length := by
    simpa [String.length_toList] using toDigits_inj hd
  obtain ⟨hx, hs⟩ := List.append_inj hr hlen
  exact ⟨String.ext hx, hs⟩

/-! ## Unfolding the key into characters -/

@[irreducible] def K (v : Val) : List Char := v.key.toList
@[irreducible] def LK (vs : List Val) : List Char := (Val.listKeys vs).toList
@[irreducible] def FK (fs : List (String × Val)) : List Char := (Val.fieldKeys fs).toList

private theorem K_literal (t j : String) : K (.literal t j) = 'L' :: (S t ++ S j) := by
  simp [K, S, Val.key, String.toList_append]
private theorem K_atom (t n o : String) (l : Option Nat) :
    K (.atom t n o l) = 'A' :: (S t ++ (S n ++ (S o ++
      (match l with | none => ['N'] | some k => 'S' :: S (toString k))))) := by
  cases l <;> simp [K, S, Val.key, String.toList_append]
private theorem K_record (t c : String) (fs : List (String × Val)) :
    K (.record t c fs) = 'R' :: (S t ++ (S c ++ ('[' :: (FK fs ++ [']'])))) := by
  simp [K, S, FK, Val.key, String.toList_append]
private theorem K_encoded (i : String) (v : Val) : K (.encoded i v) = 'E' :: (S i ++ K v) := by
  simp [K, S, Val.key, String.toList_append]
private theorem K_app (t o : String) (as : List Val) :
    K (.app t o as) = 'P' :: (S t ++ (S o ++ ('[' :: (LK as ++ [']'])))) := by
  simp [K, S, LK, Val.key, String.toList_append]
private theorem K_result (t p g : String) (fs : List (String × Val)) :
    K (.result t p g fs) = 'Q' :: (S t ++ (S p ++ (S g ++ ('[' :: (FK fs ++ [']']))))) := by
  simp [K, S, FK, Val.key, String.toList_append]
private theorem LK_nil : LK [] = [] := by simp [LK, Val.listKeys]
private theorem LK_cons (v : Val) (vs : List Val) : LK (v :: vs) = K v ++ LK vs := by
  simp [LK, K, Val.listKeys, String.toList_append]
private theorem FK_nil : FK [] = [] := by simp [FK, Val.fieldKeys]
private theorem FK_cons (n : String) (v : Val) (fs : List (String × Val)) :
    FK ((n, v) :: fs) = S n ++ (K v ++ FK fs) := by
  simp [FK, K, S, Val.fieldKeys, String.toList_append]

/-- Every key starts with its constructor tag, never with `]`. -/
private theorem K_head (v : Val) : ∃ c r, K v = c :: r ∧ c ≠ ']' := by
  cases v with
  | literal => exact ⟨_, _, K_literal .., by decide⟩
  | atom => exact ⟨_, _, K_atom .., by decide⟩
  | record => exact ⟨_, _, K_record .., by decide⟩
  | encoded => exact ⟨_, _, K_encoded .., by decide⟩
  | app => exact ⟨_, _, K_app .., by decide⟩
  | result => exact ⟨_, _, K_result .., by decide⟩

private theorem S_head_ne (s : String) : ∃ c r, S s = c :: r ∧ c ≠ ']' := by
  obtain ⟨c, r, h, hd⟩ := S_head s
  refine ⟨c, r, h, ?_⟩
  intro hc; subst hc; exact absurd hd (by decide)

private theorem close_ne_K {v : Val} {s t : List Char} : (']' :: s) ≠ K v ++ t := by
  obtain ⟨c, r, h, hc⟩ := K_head v
  rw [h]; intro he; simp only [List.cons_append, List.cons.injEq] at he; exact hc he.1.symm

private theorem close_ne_S {n : String} {s t : List Char} : (']' :: s) ≠ S n ++ t := by
  obtain ⟨c, r, h, hc⟩ := S_head_ne n
  rw [h]; intro he; simp only [List.cons_append, List.cons.injEq] at he; exact hc he.1.symm

private theorem toString_inj {m n : Nat} (h : toString m = toString n) : m = n := by
  apply toDigits_inj
  have := congrArg String.toList h
  simpa [Nat.toString_eq_repr, Nat.toList_repr] using this

/-- Constructor tag written first by `Val.key`. -/
def tag : Val → Char
  | .literal .. => 'L' | .atom .. => 'A' | .record .. => 'R'
  | .encoded .. => 'E' | .app .. => 'P' | .result .. => 'Q'

private theorem K_tag (v : Val) : ∃ r, K v = tag v :: r := by
  cases v with
  | literal => exact ⟨_, K_literal ..⟩
  | atom => exact ⟨_, K_atom ..⟩
  | record => exact ⟨_, K_record ..⟩
  | encoded => exact ⟨_, K_encoded ..⟩
  | app => exact ⟨_, K_app ..⟩
  | result => exact ⟨_, K_result ..⟩

private theorem tag_eq {a b : Val} {s t : List Char} (h : K a ++ s = K b ++ t) : tag a = tag b := by
  obtain ⟨r₁, h₁⟩ := K_tag a
  obtain ⟨r₂, h₂⟩ := K_tag b
  rw [h₁, h₂] at h
  simp only [List.cons_append, List.cons.injEq] at h
  exact h.1

/-! ## Prefix-freeness by mutual structural recursion -/

mutual
private theorem K_prefix : ∀ (a b : Val) (s t : List Char), K a ++ s = K b ++ t → a = b ∧ s = t
  | .literal t₁ j₁, b, s, t, h => by
    cases b with
    | literal t₂ j₂ =>
      rw [K_literal, K_literal] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h⟩ := S_prefix h
      obtain ⟨e₂, h⟩ := S_prefix h
      exact ⟨by rw [e₁, e₂], h⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
  | .atom t₁ n₁ o₁ l₁, b, s, t, h => by
    cases b with
    | atom t₂ n₂ o₂ l₂ =>
      rw [K_atom, K_atom] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h₁⟩ := S_prefix h
      obtain ⟨e₂, h₂⟩ := S_prefix h₁
      obtain ⟨e₃, h₃⟩ := S_prefix h₂
      clear h h₁ h₂
      subst e₁ e₂ e₃
      cases l₁ with
      | none =>
        cases l₂ with
        | none =>
          simp only [List.cons_append, List.nil_append, List.cons.injEq, true_and] at h₃
          exact ⟨rfl, h₃⟩
        | some k₂ =>
          simp only [List.cons_append, List.nil_append, List.cons.injEq] at h₃
          exact absurd h₃.1 (by decide)
      | some k₁ =>
        cases l₂ with
        | none =>
          simp only [List.cons_append, List.nil_append, List.cons.injEq] at h₃
          exact absurd h₃.1 (by decide)
        | some k₂ =>
          simp only [List.cons_append, List.cons.injEq, true_and] at h₃
          obtain ⟨ek, h₄⟩ := S_prefix h₃
          exact ⟨by rw [toString_inj ek], h₄⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
  | .record t₁ c₁ fs₁, b, s, t, h => by
    cases b with
    | record t₂ c₂ fs₂ =>
      rw [K_record, K_record] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h⟩ := S_prefix h
      obtain ⟨e₂, h⟩ := S_prefix h
      simp only [List.cons.injEq, true_and] at h
      obtain ⟨e₃, h⟩ := FK_prefix fs₁ fs₂ s t h
      exact ⟨by rw [e₁, e₂, e₃], h⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
  | .encoded i₁ v₁, b, s, t, h => by
    cases b with
    | encoded i₂ v₂ =>
      rw [K_encoded, K_encoded] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h⟩ := S_prefix h
      obtain ⟨e₂, h⟩ := K_prefix v₁ v₂ s t h
      exact ⟨by rw [e₁, e₂], h⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
  | .app t₁ o₁ as₁, b, s, t, h => by
    cases b with
    | app t₂ o₂ as₂ =>
      rw [K_app, K_app] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h⟩ := S_prefix h
      obtain ⟨e₂, h⟩ := S_prefix h
      simp only [List.cons.injEq, true_and] at h
      obtain ⟨e₃, h⟩ := LK_prefix as₁ as₂ s t h
      exact ⟨by rw [e₁, e₂, e₃], h⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
  | .result t₁ p₁ g₁ fs₁, b, s, t, h => by
    cases b with
    | result t₂ p₂ g₂ fs₂ =>
      rw [K_result, K_result] at h
      simp only [List.cons_append, List.cons.injEq, true_and, List.append_assoc] at h
      obtain ⟨e₁, h⟩ := S_prefix h
      obtain ⟨e₂, h⟩ := S_prefix h
      obtain ⟨e₃, h⟩ := S_prefix h
      simp only [List.cons.injEq, true_and] at h
      obtain ⟨e₄, h⟩ := FK_prefix fs₁ fs₂ s t h
      exact ⟨by rw [e₁, e₂, e₃, e₄], h⟩
    | _ => exact absurd (tag_eq h) (by simp [tag])
termination_by structural a => a

private theorem LK_prefix : ∀ (xs ys : List Val) (s t : List Char),
    LK xs ++ ']' :: s = LK ys ++ ']' :: t → xs = ys ∧ s = t
  | [], [], s, t, h => by simpa [LK_nil] using h
  | [], y :: ys, s, t, h => by
    rw [LK_nil, LK_cons, List.nil_append, List.append_assoc] at h
    exact absurd h close_ne_K
  | x :: xs, [], s, t, h => by
    rw [LK_nil, LK_cons, List.nil_append, List.append_assoc] at h
    exact absurd h.symm close_ne_K
  | x :: xs, y :: ys, s, t, h => by
    rw [LK_cons, LK_cons, List.append_assoc, List.append_assoc] at h
    obtain ⟨e₁, h⟩ := K_prefix x y _ _ h
    obtain ⟨e₂, h⟩ := LK_prefix xs ys s t h
    exact ⟨by rw [e₁, e₂], h⟩
termination_by structural xs => xs

private theorem FK_prefix : ∀ (xs ys : List (String × Val)) (s t : List Char),
    FK xs ++ ']' :: s = FK ys ++ ']' :: t → xs = ys ∧ s = t
  | [], [], s, t, h => by simpa [FK_nil] using h
  | [], (n, y) :: ys, s, t, h => by
    rw [FK_nil, FK_cons, List.nil_append, List.append_assoc] at h
    exact absurd h close_ne_S
  | (n, x) :: xs, [], s, t, h => by
    rw [FK_nil, FK_cons, List.nil_append, List.append_assoc] at h
    exact absurd h.symm close_ne_S
  | (n₁, x) :: xs, (n₂, y) :: ys, s, t, h => by
    rw [FK_cons, FK_cons] at h
    simp only [List.append_assoc] at h
    obtain ⟨e₀, h⟩ := S_prefix h
    obtain ⟨e₁, h⟩ := K_prefix x y _ _ h
    obtain ⟨e₂, h⟩ := FK_prefix xs ys s t h
    exact ⟨by rw [e₀, e₁, e₂], h⟩
termination_by structural xs => xs
end

/-! ## Main results -/

/-- The symbolic-equality key is injective. -/
theorem key_injective {a b : Val} (h : a.key = b.key) : a = b := by
  have h' : K a ++ [] = K b ++ [] := by simp [K, h]
  exact (K_prefix a b [] [] h').1

theorem key_eq_iff {a b : Val} : a.key = b.key ↔ a = b :=
  ⟨key_injective, fun h => h ▸ rfl⟩

/-- Key-based `BEq` (the instance used by the symbolic semantics) is structural equality. -/
theorem beq_iff_eq {a b : Val} : (a == b) = true ↔ a = b := by
  show (a.key == b.key) = true ↔ a = b
  constructor
  · intro h; exact key_injective (by simpa using h)
  · intro h; subst h; simp

end VAKE.KeyInjective
