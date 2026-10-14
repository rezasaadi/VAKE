from __future__ import annotations
try:
    from runtime_env import configured
except ImportError:
    from scripts.runtime_env import configured
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

FORMAT = "vake-scenarios-0.1"
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
STATUSES = {"active", "stopped", "rejected"}

def lean_string(s: str) -> str:
    if not isinstance(s, str):
        raise ValueError(f"expected a string, got {s!r}")
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ord(ch) < 32 or 127 <= ord(ch) < 160:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)

def natural(n) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError(f"expected a natural number, got {n!r}")
    return n

def only(obj: dict, keys: set[str], where: str) -> None:
    unknown = set(obj) - keys
    if unknown:
        raise ValueError(f"unknown field(s) {sorted(unknown)} in {where}")

def recipe(t) -> str:

    if not isinstance(t, dict) or len(t) != 1:
        raise ValueError(f"a recipe is an object with exactly one key: {t!r}")
    (kind, arg), = t.items()
    if kind == "sent":
        return f"(.sent {natural(arg)})"
    if kind == "named":
        return f"(.named {lean_string(arg)})"
    if kind == "public_key":
        return f"(.publicKey {lean_string(arg)})"
    if kind == "signing_key":
        return f"(.signingKey {lean_string(arg)})"
    if kind == "literal":
        only(arg, {"type", "json"}, "literal recipe")
        return f"(.literal {lean_string(arg['type'])} {lean_string(arg['json'])})"
    if kind == "atom":
        only(arg, {"type", "name", "length"}, "atom recipe")
        length = "none" if arg.get("length") is None else f"(some {natural(arg['length'])})"
        return f"(.atom {lean_string(arg['type'])} {lean_string(arg['name'])} {length})"
    if kind == "field":
        only(arg, {"of", "name"}, "field recipe")
        return f"(.field {recipe(arg['of'])} {lean_string(arg['name'])})"
    if kind == "decode":
        return f"(.decode {recipe(arg)})"
    if kind == "encode":
        only(arg, {"encoding", "record"}, "encode recipe")
        return f"(.encode {lean_string(arg['encoding'])} {recipe(arg['record'])})"
    if kind == "record":
        only(arg, {"constructor", "fields"}, "record recipe")
        fields = ".nil"
        for name, value in reversed(arg["fields"]):
            fields = f"(.cons {lean_string(name)} {recipe(value)} {fields})"
        return f"(.record {lean_string(arg['constructor'])} {fields})"
    if kind == "call":
        only(arg, {"primitive", "args"}, "call recipe")
        args = ".nil"
        for value in reversed(arg.get("args", [])):
            args = f"(.cons {recipe(value)} {args})"
        return f"(.call {lean_string(arg['primitive'])} {args})"
    raise ValueError(f"unsupported recipe kind {kind!r}")

def actions(spec: dict) -> list[tuple[str, str | None]]:

    result = []
    for step in spec["actions"]:
        if not isinstance(step, dict):
            raise ValueError(f"action must be an object: {step!r}")
        if "spawn" in step:
            only(step, {"spawn"}, "spawn action")
            s = step["spawn"]
            only(s, {"session", "role", "party", "parameters"}, "spawn")
            params = ", ".join(f"({lean_string(n)}, {recipe(r)})" for n, r in s.get("parameters", {}).items())
            result.append((f"(.spawn {lean_string(s['session'])} {lean_string(s['role'])} {lean_string(s['party'])} [{params}])", "spawn"))
        elif "advance" in step:
            only(step, {"advance", "events"}, "advance action")
            if not step.get("events"):
                raise ValueError("advance needs a non-empty list of expected events")
            for kind in step["events"]:
                result.append((f"(.advance {lean_string(step['advance'])})", lean_string(kind)[1:-1]))
        elif "deliver" in step:
            only(step, {"deliver", "recipe"}, "deliver action")
            result.append((f"(.deliver {lean_string(step['deliver'])} {recipe(step['recipe'])})", "deliver"))
        elif "remember" in step:
            only(step, {"remember", "recipe"}, "remember action")
            result.append((f"(.remember {lean_string(step['remember'])} {recipe(step['recipe'])})", "attacker_compute"))
        elif "reveal_state" in step:
            only(step, {"reveal_state"}, "reveal_state action")
            result.append((f"(.revealState {lean_string(step['reveal_state'])})", "reveal_state"))
        elif "corrupt" in step:
            only(step, {"corrupt"}, "corrupt action")
            result.append((f"(.corrupt {lean_string(step['corrupt'])})", "corrupt"))
        else:
            raise ValueError(f"unsupported action {step!r}")
    return result

def claim(prefix: str, final: str, c: dict) -> list[str]:

    if "name" not in c or not NAME.match(c["name"]):
        raise ValueError(f"claim needs an identifier name: {c!r}")
    name = f"{prefix}_{c['name']}"
    kinds = set(c) - {"name", "note"}
    if len(kinds) != 1:
        raise ValueError(f"claim {c['name']} must have exactly one kind")
    kind = kinds.pop()
    arg = c[kind]
    if kind == "status":
        only(arg, {"session", "is"}, "status claim")
        if arg["is"] not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        return [f"theorem {name} : (lookup {final}.sessions {lean_string(arg['session'])}).map Session.status = some .{arg['is']} := by rfl"]
    if kind == "sent_count":
        return [f"theorem {name} : {final}.sent.length = {natural(arg)} := by rfl"]
    if kind == "no_resume":
        return [f"theorem {name} : Source.localStep Symbolic.contract model environment {lean_string(arg)} {final} = .ok none := by rfl"]
    if kind == "sent_equal":
        i, j = (natural(x) for x in arg)

        return [f"theorem {name} : {i} < {final}.sent.length ∧ {j} < {final}.sent.length ∧ {final}.sent[{i}]? = {final}.sent[{j}]? :=",
                f"  ⟨by decide, by decide, by first | rfl | simp [{final}]⟩"]
    if kind == "emitted":
        names = "[" + ", ".join("[" + ", ".join(lean_string(x) for x in ev) + "]" for ev in arg) + "]"
        return [f'theorem {name} : ({final}.history.filter (fun e => e.kind == "emit")).map Event.names = {names} := by rfl']
    if kind == "accepted":
        only(arg, {"session", "target"}, "accepted claim")
        return [f"theorem {name} : targetState {final} {lean_string(arg['session'])} {lean_string(arg['target'])} = some \"accepted\" := by rfl"]
    if kind == "target_state":
        only(arg, {"session", "target", "is"}, "target_state claim")
        if arg["is"] not in ("pending", "accepted", "rejected"):
            raise ValueError("target state must be pending, accepted or rejected")
        return [f"theorem {name} : targetState {final} {lean_string(arg['session'])} {lean_string(arg['target'])} = some {lean_string(arg['is'])} := by rfl"]
    if kind == "no_accept":
        return [f'theorem {name} : ({final}.history.filter (fun e => e.kind == "accept")).length = 0 := by rfl']
    if kind in ("same_key", "different_key"):
        (s1, t1), (s2, t2) = arg
        left = f"acceptedKey {final} {lean_string(s1)} {lean_string(t1)}"
        right = f"acceptedKey {final} {lean_string(s2)} {lean_string(t2)}"
        lines = [f"theorem {name}_left_defined : ({left}).isSome = true := by rfl",
                 f"theorem {name}_right_defined : ({right}).isSome = true := by rfl"]
        if kind == "same_key":
            lines.append(f"theorem {name} : {left} = {right} := by rfl")
        else:
            lines.append(f"theorem {name}_keys : ({left}).map Val.key ≠ ({right}).map Val.key := by decide")
            lines.append(f"theorem {name} : {left} ≠ {right} := fun h => {name}_keys (congrArg (Option.map Val.key) h)")
        return lines
    if kind == "adversary_holds_key":
        only(arg, {"name", "session", "target"}, "adversary_holds_key claim")
        key = f"acceptedKey {final} {lean_string(arg['session'])} {lean_string(arg['target'])}"
        return [f"theorem {name}_defined : ({key}).isSome = true := by rfl",
                f"theorem {name} : lookup {final}.names {lean_string(arg['name'])} = {key} := by rfl"]
    raise ValueError(f"unsupported claim kind {kind!r}")

def load(path: Path, model_sha: str, profile_sha: str) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    only(spec, {"format", "description", "model_sha256", "profile_sha256", "scenarios"}, "scenario file")
    if spec.get("format") != FORMAT:
        raise ValueError(f"scenario format must be {FORMAT}")
    if spec["model_sha256"] != model_sha or spec["profile_sha256"] != profile_sha:
        raise ValueError("scenario file is bound to a different model/profile; regenerate its hashes after editing")
    seen = set()
    for scenario in spec["scenarios"]:
        only(scenario, {"name", "description", "actions", "claims"}, "scenario")
        if not NAME.match(scenario["name"]) or scenario["name"] in seen:
            raise ValueError(f"invalid or duplicate scenario name {scenario['name']!r}")
        seen.add(scenario["name"])
    return spec

def matching(root: Path, model: bytes, profile: bytes) -> Path | None:

    model_sha, profile_sha = hashlib.sha256(model).hexdigest(), hashlib.sha256(profile).hexdigest()
    for path in sorted((root / "examples" / "scenarios").glob("*.scenarios.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if spec.get("model_sha256") == model_sha and spec.get("profile_sha256") == profile_sha:
            return path
    return None

def generate(lean_dir: Path, proof_module: str, lake: str, scenario_path: Path,
             model_sha: str, profile_sha: str) -> Path:
    try:
        spec = load(scenario_path, model_sha, profile_sha)
        for scenario in spec["scenarios"]:
            actions(scenario)
            for c in scenario.get("claims", []):
                claim(scenario["name"], "w", c)
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"invalid scenario file: {error}") from error
    digest = proof_module.removeprefix("VAKE.Generated.B")
    lines = [f"import {proof_module}", "import VAKE.Proofs.Deduce",
             "set_option maxRecDepth 100000", "set_option linter.unusedSimpArgs false", "set_option maxHeartbeats 16000000",
             "namespace VAKE.Demo.Global", "open VAKE",
             f"abbrev model := VAKE.Imported.M{digest}.model",
             f"abbrev environment := VAKE.Imported.M{digest}.environment",
             f"abbrev program := VAKE.Generated.M{digest}.program",
             f"abbrev targetEnvironment := VAKE.Generated.M{digest}.environment",
             "def result (w : World) (a : Source.Action) := (Source.action Symbolic.contract model environment w a).toOption.getD (w, ⟨w.counter, [], []⟩)",
             "def targetState (w : World) (s t : String) : Option String := ((lookup w.sessions s).map (·.targets)).bind (fun ts => lookup ts t)",
             "def acceptedKey (w : World) (s t : String) : Option Val := (w.history.find? (fun ev => ev.kind == \"accept\" && ev.session == some s && ev.names == [t])).bind (·.values.head?)",
             "def events (w : World) : Lean.Json := Lean.toJson (w.history.map fun e => Lean.Json.mkObj [(\"kind\", Lean.toJson e.kind), (\"session\", Lean.toJson e.session), (\"role\", Lean.toJson e.role), (\"location\", Lean.toJson e.location), (\"names\", Lean.toJson e.names), (\"values\", Lean.toJson (e.values.map reprStr))])"]
    expanded = {}
    for scenario in spec["scenarios"]:
        prefix = scenario["name"]
        steps = actions(scenario)
        expanded[prefix] = steps
        lines.append(f"def {prefix}_w0 : World := Network.initial environment")
        lines.append(f"theorem {prefix}_initial : {prefix}_w0 = Network.initial environment := by rfl")
        for i, (action, kind) in enumerate(steps, 1):
            prev, w, rs, a = f"{prefix}_w{i-1}", f"{prefix}_w{i}", f"{prefix}_rs{i}", f"{prefix}_a{i}"
            lines.extend([f"def {a} : Source.Action := {action}", f"def {w} := (result {prev} {a}).1",
                          f"def {rs} := (result {prev} {a}).2",
                          f"theorem {prefix}_execution_{i} : Source.action Symbolic.contract model environment {prev} {a} = .ok ({w}, {rs}) := by rfl",
                          f"theorem {prefix}_commit_{i} : Source.commits Symbolic.contract model environment {prev} {a} {w} := by {'rfl' if '.advance' in action else 'trivial'}",
                          f"theorem {prefix}_event_{i} : (({w}.history.drop {prev}.history.length).map Event.kind) = [{json.dumps(kind)}] := by rfl",
                          f"theorem {prefix}_knowledge_{i} : Network.admitted Symbolic.contract model.registry environment {prev} {rs} := by admitted_search",
                          f"theorem {prefix}_step_{i} : Source.Step Symbolic.contract model environment ⟨{prev}⟩ {a} ({w}.history.drop {prev}.history.length) ⟨{w}⟩ := .commit {prefix}_execution_{i} {prefix}_commit_{i} {prefix}_knowledge_{i}"])
        count = len(steps)
        final = f"{prefix}_w{count}"
        lines.append(f"def {prefix}_actions : List Source.Action := [" + ", ".join(f"{prefix}_a{i}" for i in range(1, count + 1)) + "]")
        proof = f"(Source.Trace.nil ⟨{final}⟩)"
        for i in reversed(range(1, count + 1)):
            proof = f"(Source.Trace.cons {prefix}_step_{i} {proof})"
        lines.extend([f"theorem {prefix}_source_trace : Source.Trace Symbolic.contract model environment ⟨{prefix}_w0⟩ {prefix}_actions {final}.history ⟨{final}⟩ := by",
                      f"  exact {proof}",
                      f"theorem {prefix}_target_trace : Target.Trace Symbolic.contract program targetEnvironment ⟨{prefix}_w0⟩ ({prefix}_actions.map Translate.action) {final}.history ⟨{final}⟩ := by",
                      "  dsimp only [program, targetEnvironment]",
                      f"  rw [{proof_module}.binding, {proof_module}.profile_binding]",
                      f"  exact Proofs.finite_trace_preservation _ _ _ {prefix}_source_trace"])
        for c in scenario.get("claims", []):
            lines.extend(claim(prefix, final, c))
    lines.append("end VAKE.Demo.Global")

    defs = [line.split()[1] for line in lines if line.startswith("def ")]
    unfolds = defs + ["model", "environment", f"VAKE.Imported.M{digest}.model", f"VAKE.Imported.M{digest}.environment",
        "Source.action", "Source.commits", "Source.localStep", "Source.instruction", "Source.terminator",
        "Source.eval", "Source.evalArgs", "Source.evalFields", "Source.findBlock", "Source.waiting", "Source.bindPayload",
        "Network.recipe", "Network.recipeFields", "Network.recipes", "Network.spawn", "Network.deliver",
        "Network.applyRecipe", "Network.parameters", "Network.check", "Network.initial", "Network.remember",
        "Symbolic.contract", "Symbolic.invoke", "Symbolic.pure", "Symbolic.encode", "Symbolic.record",
        "Symbolic.project", "Symbolic.wellSized", "Symbolic.fresh", "Symbolic.width",
        "lookup", "put", "need", "updateSession", "appendEvent", "eraseObject", "Bind.bind", "Except.bind", "Functor.map", "Except.map", "Pure.pure", "Except.pure"]
    step_def = re.compile(r"(%s)_(w|rs|a)[0-9]+" % "|".join(map(re.escape, expanded)))

    raw = [x for x in lines if x.startswith(("import ", "set_option ", "namespace ", "open ", "abbrev ", "def "))
           and x != "import VAKE.Proofs.Deduce"]
    pairs, rendered = [], []
    for prefix, steps in expanded.items():
        n = len(steps)
        pairs += [f'("{prefix}_w{i}", Lean.toJson (reprStr {prefix}_w{i}))' for i in range(n + 1)]
        pairs += [f'("{prefix}_rs{i}", Lean.toJson (reprStr {prefix}_rs{i}))' for i in range(1, n + 1)]
        rendered.append(f'Lean.Json.mkObj [("name", Lean.toJson "{prefix}"), ("actions", Lean.toJson ({prefix}_actions.map reprStr)), ("events", events {prefix}_w{n}), ("send_count", Lean.toJson {prefix}_w{n}.sent.length)]')
    raw += ['def main : IO Unit := IO.println ((Lean.Json.mkObj [("states", Lean.Json.mkObj [' + ", ".join(pairs) + ']), ("scenarios", Lean.toJson [' + ", ".join(rendered) + '])]).compress)',
            "end VAKE.Demo.Global", "def main := VAKE.Demo.Global.main"]
    raw_path = lean_dir / "TraceCandidate.lean"
    raw_path.write_text("\n".join(raw) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = str(Path(lake).resolve().parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run([lake, "env", "lean", "--run", raw_path.name], cwd=lean_dir, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    (lean_dir / "candidate-stdout.log").write_text(proc.stdout, encoding="utf-8")
    (lean_dir / "candidate-stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError("Candidate evaluation failed; inspect candidate logs")
    candidate = json.loads(proc.stdout)
    descriptions = {s["name"]: s.get("description", "") for s in spec["scenarios"]}
    claims = {s["name"]: [c["name"] for c in s.get("claims", [])] for s in spec["scenarios"]}
    for s in candidate["scenarios"]:
        s["description"] = descriptions[s["name"]]
        s["claims"] = claims[s["name"]]
    (lean_dir / "trace-candidate.json").write_text(json.dumps({"status": "EXECUTABLE_CANDIDATE", "scenario_file": scenario_path.name,
        "scenarios": candidate["scenarios"]}, indent=2) + "\n", encoding="utf-8")
    worlds = candidate["states"]

    available, rewritten = set(), []
    for line in lines:
        if line.startswith("def "):
            available.add(line.split()[1])
        names = [n for n in unfolds if n not in defs or n in available]
        names = [n for n in names if not step_def.fullmatch(n) or re.search(r"\b" + n + r"\b", line)]
        if line.startswith("def ") and line.split()[1] in worlds:
            name = line.split()[1]
            line = f"def {name} : {'Network.RecipeState' if '_rs' in name else 'World'} := {worlds[name].replace(chr(10), ' ')}"
        if line.endswith(":= by rfl"):
            line = line[:-len("by rfl")] + "by first | rfl | simp [" + ", ".join(names) + "] <;> rfl"
        rewritten.append(line)
    path = lean_dir / "VAKE/Demo/Global.lean"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return path

def required_theorems(spec_path: Path, candidate: dict) -> list[str]:

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    claims = {s["name"]: s.get("claims", []) for s in spec["scenarios"]}
    names = []
    for scenario in candidate["scenarios"]:
        prefix = "VAKE.Demo.Global." + scenario["name"]
        names += [prefix + "_initial", prefix + "_source_trace", prefix + "_target_trace"]
        names += [prefix + suffix + str(i + 1) for i in range(len(scenario["actions"]))
                  for suffix in ("_execution_", "_commit_", "_event_", "_knowledge_", "_step_")]
        names += [prefix + "_" + c["name"] for c in claims[scenario["name"]]]
    return names

if __name__ == "__main__":
    import sys
    lean_dir, proof_module, scenarios, model_sha, profile_sha = sys.argv[1:6]
    generate(Path(lean_dir), proof_module, configured("LAKE", "lake"), Path(scenarios), model_sha, profile_sha)
