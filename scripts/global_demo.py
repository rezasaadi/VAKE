from runtime_env import configured
from pathlib import Path
import json
import os
import re
import subprocess

def generate(lean_dir: Path, proof_module: str, lake: str):
    digest = proof_module.removeprefix("VAKE.Generated.B")
    lines = [f"import {proof_module}",
             "set_option maxRecDepth 100000", "set_option linter.unusedSimpArgs false", "set_option maxHeartbeats 16000000",
             "namespace VAKE.Demo.Global", "open VAKE",
             f"abbrev model := VAKE.Imported.M{digest}.model",
             f"abbrev environment := VAKE.Imported.M{digest}.environment",
             f"abbrev program := VAKE.Generated.M{digest}.program",
             f"abbrev targetEnvironment := VAKE.Generated.M{digest}.environment",
             "def result (w : World) (a : Source.Action) := (Source.action Symbolic.contract model environment w a).toOption.getD (w, ⟨w.counter, [], []⟩)",
             "def events (w : World) : Lean.Json := Lean.toJson (w.history.map fun e => Lean.Json.mkObj [(\"kind\", Lean.toJson e.kind), (\"session\", Lean.toJson e.session), (\"role\", Lean.toJson e.role), (\"location\", Lean.toJson e.location), (\"names\", Lean.toJson e.names), (\"values\", Lean.toJson (e.values.map reprStr))])"]
    scenarios = {
        "honest": [('(.spawn "A1" "Announcer" "Alice" [])', "spawn"), ('(.spawn "B1" "Echoer" "Bob" [])', "spawn")]
                  + [('(.advance "A1")', k) for k in ["sample","assign","assign","send","erase","stop"]]
                  + [('(.deliver "B1" (.sent 0))', "deliver")]
                  + [('(.advance "B1")', k) for k in ["receive","invoke","match","emit","send","stop"]],
        "malformed": [('(.spawn "B1" "Echoer" "Bob" [])', "spawn"),
                      ('(.deliver "B1" (.encode "envelopeCodec" (.record "MkEnvelope" (.cons "nonce" (.atom "Nonce" "short" (some 1)) .nil))))', "deliver")]
                  + [('(.advance "B1")', k) for k in ["receive","invoke","match","reject"]]
    }
    for scenario, actions in scenarios.items():
        prefix = scenario
        lines.append(f"def {prefix}_w0 : World := Network.initial environment")
        lines.append(f"theorem {prefix}_initial : {prefix}_w0 = Network.initial environment := by rfl")
        for i, (action, kind) in enumerate(actions, 1):
            prev, w, rs, a = f"{prefix}_w{i-1}", f"{prefix}_w{i}", f"{prefix}_rs{i}", f"{prefix}_a{i}"
            lines.extend([f"def {a} : Source.Action := {action}", f"def {w} := (result {prev} {a}).1",
                          f"def {rs} := (result {prev} {a}).2",
                          f"theorem {prefix}_execution_{i} : Source.action Symbolic.contract model environment {prev} {a} = .ok ({w}, {rs}) := by rfl",
                          f"theorem {prefix}_commit_{i} : Source.commits Symbolic.contract model environment {prev} {a} {w} := by {'rfl' if '.advance' in action else 'trivial'}",
                          f"theorem {prefix}_event_{i} : (({w}.history.drop {prev}.history.length).map Event.kind) = [{json.dumps(kind)}] := by rfl",
                          f"theorem {prefix}_knowledge_{i} : Network.admitted Symbolic.contract model.registry environment {prev} {rs} := by"])
            if ".deliver" not in action:
                lines.append(f"  intro extra v h; exact False.elim (List.not_mem_nil h)")
            elif scenario == "honest":
                lines.extend([f"  intro extra v h",
                              ""])
                lines[-1] = f"  have eq : (extra, v) = ([], {prev}.sent[0]!) := List.mem_singleton.mp h"
                lines += ["  cases eq", "  apply Network.Deducible.root", "  exact List.mem_cons_of_mem _ (List.mem_cons_of_mem _ (List.mem_cons_self))"]
            else:
                lines.extend(["  intro extra v h",
                    '  have members : (extra, v) = ([Val.atom "Nonce" "short" "adversary" (some 1)], Val.record "Envelope" "MkEnvelope" [("nonce", Val.atom "Nonce" "short" "adversary" (some 1))]) ∨ (extra, v) = ([Val.atom "Nonce" "short" "adversary" (some 1)], Val.encoded "envelopeCodec" (.record "Envelope" "MkEnvelope" [("nonce", Val.atom "Nonce" "short" "adversary" (some 1))])) := by simpa only [malformed_rs2, List.mem_cons, List.not_mem_nil, or_false] using h',
                    "  rcases members with eq | eq",
                    "  · cases eq",
                    '    apply Network.Deducible.record "MkEnvelope" [("nonce", Val.atom "Nonce" "short" "adversary" (some 1))]',
                    '    · intro n x hx; have pair := List.mem_singleton.mp hx; cases pair; exact Network.Deducible.root _ (List.mem_append_right _ (List.mem_singleton_self _))',
                    "    · rfl",
                    "  · cases eq",
                    '    apply Network.Deducible.encode "envelopeCodec" (.record "Envelope" "MkEnvelope" [("nonce", Val.atom "Nonce" "short" "adversary" (some 1))])',
                    '    · apply Network.Deducible.record "MkEnvelope" [("nonce", Val.atom "Nonce" "short" "adversary" (some 1))]',
                    '      · intro n x hx; have pair := List.mem_singleton.mp hx; cases pair; exact Network.Deducible.root _ (List.mem_append_right _ (List.mem_singleton_self _))',
                    "      · rfl",
                    "    · rfl"])
            lines.extend([f"theorem {prefix}_step_{i} : Source.Step Symbolic.contract model environment ⟨{prev}⟩ {a} ({w}.history.drop {prev}.history.length) ⟨{w}⟩ := .commit {prefix}_execution_{i} {prefix}_commit_{i} {prefix}_knowledge_{i}"])
        count = len(actions)
        actionlist = "[" + ", ".join(f"{prefix}_a{i}" for i in range(1,count+1)) + "]"
        lines.append(f"def {prefix}_actions : List Source.Action := {actionlist}")
        proof = f"(Source.Trace.nil ⟨{prefix}_w{count}⟩)"
        for i in reversed(range(1,count+1)):
            proof = f"(Source.Trace.cons {prefix}_step_{i} {proof})"
        lines.extend([f"theorem {prefix}_source_trace : Source.Trace Symbolic.contract model environment ⟨{prefix}_w0⟩ {prefix}_actions {prefix}_w{count}.history ⟨{prefix}_w{count}⟩ := by",
                      f"  exact {proof}",
                      f"theorem {prefix}_target_trace : Target.Trace Symbolic.contract program targetEnvironment ⟨{prefix}_w0⟩ ({prefix}_actions.map Translate.action) {prefix}_w{count}.history ⟨{prefix}_w{count}⟩ := by",
                      "  dsimp only [program, targetEnvironment]",
                      f"  rw [{proof_module}.binding, {proof_module}.profile_binding]",
                      f"  exact Proofs.finite_trace_preservation _ _ _ {prefix}_source_trace",
                      f"theorem {prefix}_echoer_outcome : (lookup {prefix}_w{count}.sessions \"B1\").map Session.status = some .{'stopped' if scenario=='honest' else 'rejected'} := by rfl",
                      f"theorem {prefix}_send_count : {prefix}_w{count}.sent.length = {2 if scenario=='honest' else 0} := by rfl",
                      f"theorem {prefix}_echoer_no_resume : Source.localStep Symbolic.contract model environment \"B1\" {prefix}_w{count} = .ok none := by rfl"])
        if scenario == "honest":
            lines.extend([f'theorem honest_announcer_stopped : (lookup {prefix}_w{count}.sessions "A1").map Session.status = some .stopped := by rfl',
                          f"theorem honest_echo_equals_announcement : {prefix}_w{count}.sent[0]? = {prefix}_w{count}.sent[1]? := by rfl",
                          f'theorem honest_observation : ({prefix}_w{count}.history.filter (fun e => e.kind == "emit")).map Event.names = [["NonceObserved"]] := by rfl'])
    lines.append("end VAKE.Demo.Global")

    defs = [line.split()[1] for line in lines if line.startswith("def ")]
    unfolds = defs + ["model", "environment", f"VAKE.Imported.M{digest}.model", f"VAKE.Imported.M{digest}.environment",
        "Source.action", "Source.commits", "Source.localStep", "Source.instruction", "Source.terminator",
        "Source.eval", "Source.evalArgs", "Source.evalFields", "Source.findBlock", "Source.waiting", "Source.bindPayload",
        "Network.recipe", "Network.recipeFields", "Network.recipes", "Network.spawn", "Network.deliver",
        "Network.applyRecipe", "Network.parameters", "Network.check", "Network.initial",
        "Symbolic.contract", "Symbolic.invoke", "Symbolic.pure", "Symbolic.encode", "Symbolic.record",
        "Symbolic.project", "Symbolic.wellSized", "Symbolic.fresh", "Symbolic.width",
        "lookup", "put", "need", "updateSession", "appendEvent", "eraseObject", "Bind.bind", "Except.bind", "Functor.map", "Except.map", "Pure.pure", "Except.pure"]

    raw = [x for x in lines if x.startswith(("import ", "set_option ", "namespace ", "open ", "abbrev ", "def "))]
    pairs = []
    rendered = []
    for scenario, actions in scenarios.items():
        n = len(actions)
        for i in range(n+1): pairs.append(f'("{scenario}_w{i}", Lean.toJson (reprStr {scenario}_w{i}))')
        for i in range(1,n+1): pairs.append(f'("{scenario}_rs{i}", Lean.toJson (reprStr {scenario}_rs{i}))')
        rendered.append(f'Lean.Json.mkObj [("name", Lean.toJson "{scenario}"), ("actions", Lean.toJson ({scenario}_actions.map reprStr)), ("events", events {scenario}_w{n}), ("send_count", Lean.toJson {scenario}_w{n}.sent.length)]')
    raw += ['def main : IO Unit := IO.println ((Lean.Json.mkObj [("states", Lean.Json.mkObj [' + ", ".join(pairs) + ']), ("scenarios", Lean.toJson [' + ", ".join(rendered) + '])]).compress)',
            "end VAKE.Demo.Global", "def main := VAKE.Demo.Global.main"]
    raw_path = lean_dir / "TraceCandidate.lean"
    raw_path.write_text("\n".join(raw)+"\n", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = str(Path(lake).resolve().parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run([lake, "env", "lean", "--run", raw_path.name], cwd=lean_dir, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    (lean_dir / "candidate-stdout.log").write_text(proc.stdout, encoding="utf-8")
    (lean_dir / "candidate-stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode: raise RuntimeError("Candidate evaluation failed; inspect candidate logs")
    candidate = json.loads(proc.stdout)
    (lean_dir / "trace-candidate.json").write_text(json.dumps({"status":"EXECUTABLE_CANDIDATE", "scenarios":candidate["scenarios"]}, indent=2)+"\n",encoding="utf-8")
    worlds = candidate["states"]

    available = set()
    rewritten = []
    for line in lines:
        if line.startswith("def "): available.add(line.split()[1])
        names = [n for n in unfolds if n not in defs or n in available]
        names = [n for n in names if not re.fullmatch("(honest|malformed)_(w|rs|a)[0-9]+",n) or re.search(r"\b"+n+r"\b",line)]
        if line.startswith("def ") and line.split()[1] in worlds:
            name = line.split()[1]
            value = worlds[name].replace(chr(10), " ")
            line = f"def {name} : {'Network.RecipeState' if '_rs' in name else 'World'} := {value}"
        tactic = "simp [" + ", ".join(names) + "]"
        if line.endswith(":= by rfl"):
            line = line[:-len("by rfl")] + "by first | rfl | " + tactic + " <;> rfl"
        if "intro extra v h; exact False.elim" in line:
            line = "  intro extra v h; first | exact False.elim (List.not_mem_nil h) | " + tactic + " at h"
        rewritten.append(line)
    lines = rewritten
    path = lean_dir / "VAKE/Demo/Global.lean"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]), sys.argv[2], configured('LAKE', "lake"))

