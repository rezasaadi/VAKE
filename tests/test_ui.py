from contextlib import contextmanager
from pathlib import Path
import hashlib
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from ui.runner import ROOT, Store, MAX_INPUT, safe, read_json, write_json, sha
from ui.server import Server
from scripts.runtime_env import configured

class UITests(unittest.TestCase):
    def setUp(self):

        parent = ROOT / "reports/ui-runs"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="test-", dir=parent)
        self.store = Store(runs=Path(self.temp.name) / "runs", timeout=int(configured("UI_TEST_TIMEOUT", "180" if os.name == "nt" else "900")))
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def run_stage(self, run_id, name):
        self.store.start(run_id, name)
        deadline = time.monotonic() + self.store.timeout + 30
        while time.monotonic() < deadline:
            result = self.store.refresh(run_id)
            if result["job"]["state"] not in ("queued", "running"):
                return result
            time.sleep(.05)
        self.fail("UI stage did not finish")
    def example(self, example="nonce_exchange", **kw):
        return self.store.create({"example": example, **kw})["run_id"]
    def test_real_check_and_exact_inputs(self):
        rid = self.example()
        result = self.run_stage(rid, "check")
        self.assertEqual(result["result"]["frontend_status"], "CHECKED")
        self.assertEqual(result["stages"][0]["exit_code"], 0)
        self.assertEqual(result["source_sha256"], sha((ROOT / "examples/nonce_exchange.json").read_bytes()))
        self.assertTrue(result["terminal_demo_eligible"])
        self.assertEqual(result["schema"], "0.1")
        self.assertEqual(result["result"]["security_status"], "OPEN_OBLIGATION")
    def test_open_obligation_retains_exit_two_and_blocks_verify(self):
        model=json.loads((ROOT/"examples/public_message.json").read_text(encoding="utf-8"))
        model["holes"]=[{"id":"missingPayload","object_path":"/roles/0/blocks/0/steps/0/term",
                        "expected_type_id":"Bytes","reason":"Deliberately open test","blocked_obligation_ids":[]}]
        model["roles"][0]["blocks"][0]["steps"][0]["term"]={"kind":"hole","hole_id":"missingPayload","type_id":"Bytes"}
        rid=self.store.create({"model":json.dumps(model)})["run_id"]
        result=self.run_stage(rid,"check")
        self.assertEqual((result["result"]["frontend_status"],result["stages"][0]["exit_code"]),("OPEN_OBLIGATION",2))
        self.run_stage(rid,"export")
        with self.assertRaisesRegex(ValueError,"open obligations"): self.store.start(rid,"verify")
    def test_changed_saved_input_refuses_execution(self):
        rid=self.example()
        (self.store.directory(rid)/"model.json").write_text("{}",encoding="utf-8")
        result=self.run_stage(rid,"check")
        self.assertEqual(result["result"]["frontend_status"],"INTERNAL_ERROR")
        self.assertIn("identity changed",result["stages"][0]["message"])
    def test_real_negative_control(self):
        result = self.run_stage(self.example("type_mismatch"), "check")
        stage = result["stages"][0]
        self.assertEqual((stage["status"],stage["exit_code"]), ("TYPE_ERROR",1))
        self.assertTrue(stage["meets_expected"])
        self.assertEqual(result["job"]["state"], "completed")
        with self.assertRaises(ValueError):
            self.store.start(result["run_id"], "export")
    def test_real_malformed_json(self):
        rid = self.store.create({"model": "{broken"})["run_id"]
        result = self.run_stage(rid, "check")
        self.assertEqual(result["result"]["frontend_status"], "PARSE_ERROR")
        self.assertEqual(result["stages"][0]["exit_code"], 1)
    def test_real_invalid_profile(self):
        rid = self.example(profile='{"schema_version":"1.0","interpretation":"unsupported"}')
        self.run_stage(rid, "check")
        result = self.run_stage(rid, "export")
        self.assertEqual(result["result"]["export_status"], "UNSUPPORTED")
        self.assertFalse(result["terminal_demo_eligible"])
        self.assertEqual(result["result"]["certificate_status"], "NOT_CHECKED")
    def test_real_export_and_repeat_no_overwrite(self):
        rid = self.example()
        self.run_stage(rid,"check")
        result = self.run_stage(rid,"export")
        self.assertEqual(result["result"]["export_status"],"EXPORTED")
        self.assertEqual(result["result"]["export_proof_status"],"NOT_CHECKED")
        self.assertTrue(any(a["path"].endswith(".lean") for a in result["artifacts"]))
        before = (self.store.directory(rid)/"stages/export/result.json").read_bytes()
        self.store.start(rid,"export")
        self.assertEqual(before,(self.store.directory(rid)/"stages/export/result.json").read_bytes())
        self.assertNotEqual(rid,self.example())
    def test_missing_binary_is_explicit(self):
        self.store.binary = str(Path(self.temp.name)/"absent-vake")
        result = self.run_stage(self.example(),"check")
        self.assertEqual(result["result"]["frontend_status"],"INTERNAL_ERROR")
        self.assertIn("message",result["stages"][0])
        self.assertIsNone(result["stages"][0]["exit_code"])
    def test_missing_lean_is_explicit(self):
        self.store.env["VAKE_LAKE"]=str(Path(self.temp.name)/"absent-lake")
        rid=self.example()
        self.run_stage(rid,"check")
        self.run_stage(rid,"export")
        result=self.run_stage(rid,"verify")
        self.assertEqual(result["result"]["certificate_status"],"INCONCLUSIVE")
        self.assertIsNone(result["audit"])
        self.assertTrue(result["missing_evidence"])
        self.assertTrue((self.store.directory(rid)/"export/verification-result.json").is_file())
    @unittest.skipUnless(configured("UI_TEST_LEAN") == "1", "Set VAKE_UI_TEST_LEAN=1 for actual Lean checks")
    def test_real_global_traces_controls_and_false_event_rejection(self):
        rid=self.example()
        for name in ("trace","controls"):
            with self.assertRaisesRegex(ValueError,"Complete Lean verification"):
                self.store.start(rid,name)
        for name in ("check","export","verify","trace","controls"):
            result=self.run_stage(rid,name)
            self.assertTrue(result["stages"][-1]["meets_expected"],result["stages"][-1])
        self.assertEqual(result["result"]["negative_binding_controls"],"PASSED")
        self.assertEqual(len(result["controls"]["controls"]),2)
        trace=result["trace"]
        self.assertEqual(trace["status"],"PROVED_UNDER_ASSUMPTIONS")
        self.assertEqual([(r["name"],len(r["events"]),r["send_count"]) for r in trace["scenarios"]],[("honest",15,2),("malformed",6,0)])
        self.assertEqual(trace["scenarios"][1]["events"][-1]["kind"],"reject")
        self.assertEqual(trace["security_status"],"OPEN_OBLIGATION")
        path=self.store.directory(rid)/"traces/lean-check"
        certificate=(path/"VAKE/Demo/Global.lean").read_text(encoding="utf-8")
        self.assertEqual(certificate.count('= ["emit"]'),1)
        (path/"FalseEvent.lean").write_text(certificate.replace('= ["emit"]','= ["send"]'),encoding="utf-8")
        proc=subprocess.run([configured("LAKE","lake"),"env","lean","FalseEvent.lean"],cwd=path,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=self.store.timeout)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn("error:",proc.stdout)
        self.assertIn("Tactic",proc.stdout)

        original=(self.store.directory(rid)/"stages/controls/result.json").read_bytes()
        self.store.start(rid,"controls")
        self.assertEqual(original,(self.store.directory(rid)/"stages/controls/result.json").read_bytes())

    @unittest.skipUnless(configured("UI_TEST_LEAN") == "1", "Actual Lean integration opt-in")
    def test_signature_example_scope(self):
        rid=self.example("signature_check")
        for name in ("check","export","verify"):
            result=self.run_stage(rid,name)
            self.assertTrue(result["stages"][-1]["meets_expected"],result["stages"][-1])
        self.assertFalse(result["terminal_demo_eligible"])
        self.assertIn("VAKE.Demo.Signature.sign_constructs_signature",{x["name"] for x in result["audit"]["theorems"]})
        with self.assertRaisesRegex(ValueError,"bundled scenario file"): self.store.start(rid,"trace")
        observations=read_json(self.store.directory(rid)/"export/lean-check/validation/signature-observations.json")
        self.assertEqual(observations["status"],"EXECUTABLE_OBSERVATION")
        self.assertIn('"ok"',observations["valid"])
        self.assertIn('"invalid"',observations["changed_message"])
        self.assertEqual(result["result"]["security_status"],"OPEN_OBLIGATION")

    def test_oversize_and_invalid_input_shapes(self):
        for body in ({"model":" "* (MAX_INPUT+1)},{"model":"{}","profile":" "*(MAX_INPUT+1)},
                     {"model":None},{"example":"../../secret"},{"model":"{}","profile":[]}):
            with self.assertRaises(ValueError): self.store.create(body)
    def test_artifact_traversal(self):
        rid=self.example()
        with self.assertRaises(ValueError): self.store.directory("../outside")
        for path in ("../outside.json","C:/outside.json",r"..\outside.json"):
            with self.assertRaises(ValueError): safe(self.store.directory(rid),path)
        with self.assertRaises(FileNotFoundError): self.store.artifact(rid,"model.json")
    def test_symlink_escape(self):
        rid=self.example()
        outside=Path(self.temp.name)/"private.json"
        outside.write_text("private",encoding="utf-8")
        link=self.store.directory(rid)/"escape.json"
        try: link.symlink_to(outside)
        except OSError:
            self.skipTest("Host does not permit creating symlinks; run this test on Linux or a symlink-capable Windows host")
        with self.assertRaises(ValueError): safe(self.store.directory(rid),"escape.json")
        self.assertFalse(any(a["path"]=="escape.json" for a in self.store.refresh(rid)["artifacts"]))
    def test_durable_history_restart_and_exclusive_store(self):
        rid=self.example()
        self.run_stage(rid,"check")
        with self.assertRaisesRegex(ValueError,"already in use"):
            Store(runs=self.store.runs)
        directory=self.store.runs
        self.store.close()
        self.store=Store(runs=directory)
        self.assertEqual(self.store.history()[0]["run_id"],rid)
        self.assertEqual(self.store.refresh(rid)["result"]["frontend_status"],"CHECKED")
    def test_interrupted_run_retains_failed_history(self):
        rid=self.example()
        path=self.store.directory(rid)
        state=read_json(path/"state.json")
        state["job"]={"state":"running","stage":"check"}
        write_json(path/"state.json",state)
        directory=self.store.runs
        self.store.close()
        self.store=Store(runs=directory)
        self.assertEqual(self.store.refresh(rid)["result"]["frontend_status"],"INCONCLUSIVE")
    def test_bundle_hashes_paths_and_determinism(self):
        rid=self.example()
        self.run_stage(rid,"check")
        self.run_stage(rid,"export")
        data=self.store.bundle(rid)
        self.assertEqual(data,self.store.bundle(rid))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            manifest=json.loads(z.read("run-manifest.json"))
            for row in manifest["artifacts"]:
                content=z.read(row["path"])
                self.assertEqual(sha(content),row["sha256"])
                self.assertEqual(len(content),row["bytes"])
                self.assertNotIn(str(Path.home()).encode(),content)
            self.assertEqual(z.read("model.json"),(ROOT/"examples/nonce_exchange.json").read_bytes())
            self.assertEqual(z.read("profile.json"),(ROOT/"examples/restricted_symbolic_v1.profile.json").read_bytes())
    @unittest.skipUnless(configured("UI_TEST_LEAN") == "1", "Actual Lean integration opt-in")
    def test_dh_example_traces_from_bundled_scenarios(self):
        rid=self.example("dh_exchange")
        self.assertTrue(self.store.refresh(rid)["trace_eligible"])
        for name in ("check","export","verify","trace"):
            result=self.run_stage(rid,name)
            self.assertTrue(result["stages"][-1]["meets_expected"],result["stages"][-1])
        with self.assertRaisesRegex(ValueError,"Binding controls require"): self.store.start(rid,"controls")
        trace=result["trace"]
        self.assertEqual(trace["status"],"PROVED_UNDER_ASSUMPTIONS")
        self.assertEqual([(r["name"],len(r["events"]),r["send_count"]) for r in trace["scenarios"]],[("honest",32,2),("mitm",35,2)])
        self.assertIn("VAKE.Demo.Global.mitm_keys_differ",{x["name"] for x in json.loads((self.store.directory(rid)/"traces/lean-check/validation/proof-audit.json").read_text())["theorems"]})
        self.assertEqual(trace["security_status"],"OPEN_OBLIGATION")

    @unittest.skipUnless(configured("UI_TEST_LEAN") == "1", "Actual Lean integration opt-in")
    def test_signed_dh_browser_workflow_and_evidence(self):
        rid=self.example("signed_dh_exchange")
        state=self.store.refresh(rid)
        self.assertTrue(state["trace_eligible"])
        self.assertFalse(state["terminal_demo_eligible"])
        for stage in ("check","export","verify","trace"):
            result=self.run_stage(rid,stage)
            self.assertTrue(result["stages"][-1]["meets_expected"],result["stages"][-1])
        self.assertEqual(result["trace"]["status"],"PROVED_UNDER_ASSUMPTIONS")
        self.assertEqual([s["name"] for s in result["trace"]["scenarios"]],["honest","forged_share","spliced_signature"])
        names={row["name"] for row in result["trace_audit"]["theorems"]}
        self.assertTrue({"VAKE.Demo.Global.honest_keys_agree","VAKE.Demo.Global.forged_share_no_key_accepted","VAKE.Demo.Global.spliced_signature_no_key_accepted"}<=names)
        self.assertEqual(result["security_status"],"OPEN_OBLIGATION")
        with zipfile.ZipFile(io.BytesIO(self.store.bundle(rid))) as archive:
            manifest=json.loads(archive.read("run-manifest.json"))
            for row in manifest["artifacts"]:
                self.assertEqual(hashlib.sha256(archive.read(row["path"])).hexdigest(),row["sha256"])
            self.assertEqual(archive.read("model.json"),(ROOT/"examples/signed_dh_exchange.json").read_bytes())

    def test_exact_demo_scope_requires_both_inputs(self):
        data=(ROOT/"examples/nonce_exchange.json").read_text(encoding="utf-8")
        rid=self.store.create({"model":data+"\n"})["run_id"]
        state=self.store.refresh(rid)
        self.assertFalse(state["terminal_demo_eligible"])
        self.assertFalse(state["trace_eligible"])
        self.assertNotIn("--terminal-demo",self.store.command(self.store.directory(rid),"verify",state))
    def test_timeout_reports_inconclusive(self):
        rid=self.example()
        original=self.store.command

        self.store.command=lambda path,name,state:[sys.executable,"-c","import time; time.sleep(20)"]
        self.store.timeout=.1
        result=self.run_stage(rid,"check")
        self.assertEqual(result["result"]["frontend_status"],"INCONCLUSIVE")
        self.assertFalse(result["stages"][0]["meets_expected"])
        self.assertFalse(self.store.processes)
        self.store.command=original
    @contextmanager
    def http(self):
        server=Server(0,self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try: yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    def request(self,server,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=10)
        data=None if body is None else json.dumps(body).encode()
        hdr={"Content-Type":"application/json"}
        hdr.update(headers or {})
        connection.request(method,path,data,hdr)
        response=connection.getresponse()
        status,content=response.status,response.read()
        connection.close()
        return status,content
    def test_http_start_stop_examples_host_origin_and_occupied_port(self):
        with self.http() as server:
            self.assertEqual(server.server_address[0],"127.0.0.1")
            self.assertEqual(self.request(server,"GET","/api/health")[0],200)
            code,content=self.request(server,"GET","/api/examples")
            self.assertEqual(code,200)
            self.assertEqual(json.loads(content)[0]["model"],(ROOT/"examples/nonce_exchange.json").read_text(encoding="utf-8"))
            self.assertEqual(self.request(server,"POST","/api/runs",{"example":"nonce_exchange"})[0],201)
            self.assertEqual(self.request(server,"GET","/api/health",headers={"Host":"evil.invalid"})[0],403)
            self.assertEqual(self.request(server,"POST","/api/runs",{},{"Origin":"https://evil.invalid"})[0],403)
            self.assertEqual(self.request(server,"POST","/api/runs",{"model":"x"*8192},{"Origin":"https://evil.invalid"})[0],403)
            self.assertEqual(self.request(server,"GET","/../../Cargo.toml")[0],400)
            self.assertEqual(self.request(server,"GET","/api/runs/x/files/%2e%2e")[0],400)
            with self.assertRaises(OSError): Server(server.server_port,self.store)
    @unittest.skipUnless(configured("UI_TEST_LEAN")=="1","Set VAKE_UI_TEST_LEAN=1 for real fresh Lean integration")
    def test_real_lean_certificates(self):
        rid=self.example()
        for action in ("check","export","verify"): result=self.run_stage(rid,action)
        self.assertEqual(result["result"]["certificate_status"],"PROVED_UNDER_ASSUMPTIONS")
        self.assertEqual(result["result"]["theorem_count"],len(result["audit"]["theorems"]))
        self.assertTrue(result["result"]["terminal_demo"])
        self.assertEqual(result["result"]["security_status"],"OPEN_OBLIGATION")
        self.assertTrue(all(t["kernel_checked"] for t in result["audit"]["theorems"]))
        with zipfile.ZipFile(io.BytesIO(self.store.bundle(rid))) as z:
            manifest=json.loads(z.read("run-manifest.json"))
            for a in manifest["artifacts"]: self.assertEqual(sha(z.read(a["path"])),a["sha256"])

    def test_container_bind_retains_host_origin_and_fetch_guards(self):
        server=Server(0,self.store,"0.0.0.0")
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            code,data=self.request(server,"GET","/api/health")
            self.assertEqual((code,json.loads(data)["bind"]),(200,"0.0.0.0"))
            for headers in ({"Host":"evil.invalid"},{"Origin":"https://evil.invalid"},{"Sec-Fetch-Site":"cross-site"},{"Host":f"0.0.0.0:{server.server_port}"}):
                self.assertEqual(self.request(server,"GET","/api/health",headers=headers)[0],403)
            self.assertEqual(self.request(server,"POST","/api/runs",{"example":"nonce_exchange"},{"Origin":f"http://127.0.0.1:{server.server_port}"})[0],201)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_tour_routes_preserve_static_allowlist_and_request_guards(self):
        with self.http() as server:
            code, content = self.request(server, "GET", "/tour")
            self.assertEqual(code, 200)
            self.assertIn(b"Try VAKE with a nonce exchange.", content)
            self.assertIn(b'href="/#tour"', content)
            code, content = self.request(server, "GET", "/tour-images/01-open.jpg")
            self.assertEqual(code, 200)
            self.assertEqual(content, (ROOT/"docs/onboarding/01-open.jpg").read_bytes())
            self.assertEqual(content[:2], b"\xff\xd8")
            for path in ("/tour", "/tour-images/01-open.jpg"):
                for headers in ({"Host":"evil.invalid"}, {"Origin":"https://evil.invalid"}, {"Sec-Fetch-Site":"cross-site"}):
                    self.assertEqual(self.request(server,"GET",path,headers=headers)[0],403)
            for path in ("/tour-images/README.md", "/tour-images/Cargo.toml", "/tour-images/unknown.jpg"):
                self.assertEqual(self.request(server,"GET",path)[0],404)
            for path in ("/tour-images/../README.md", "/tour-images/%2e%2e/README.md"):
                self.assertEqual(self.request(server,"GET",path)[0],400)

    def test_invalid_bind_is_rejected(self):
        for address in ("localhost","::","192.0.2.1"):
            with self.assertRaisesRegex(ValueError,"Bind must"):
                Server(0,self.store,address)

    def test_public_cli_identity(self):
        p=subprocess.run([self.store.binary,"--version"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0);self.assertEqual(p.stdout.strip(),"VAKE 0.2.0")
        p=subprocess.run([self.store.binary,"--help"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)
        self.assertIn("vake check",p.stdout)
        self.assertIn("vake verify",p.stdout)

if __name__=="__main__": unittest.main()
