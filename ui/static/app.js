"use strict";
const $ = id => document.getElementById(id);
const names = ["Open model","Check model","Create Lean files","Run Lean","Execution","Evidence"];
const nextNames = ["Check the model","Create Lean files","Run the Lean checks","Inspect the execution","Save the evidence",""];
let page = 1, run = null, examples = [], artifactText = "", exportText = "", polling = null;
let tourActive = localStorage.getItem("vake-tour") === "true";
const tourSteps = [
  {title:"Your example is ready", text:"This is a fresh nonce-exchange run. Look at its roles, then continue to the model check.", target:"tour-next"},
  {title:"Check the model", text:"Select Check model. Continue after the syntax, types, and supported operations are accepted.", target:"run-check", stage:"check"},
  {title:"Create the Lean files", text:"Select Create Lean files. This translates the input; the proof check comes next.", target:"run-export", stage:"export"},
  {title:"Run the Lean checks", text:"Select Run Lean checks and wait for the result. The checks validate bindings and named certificates under the reported assumptions.", target:"run-verify", stage:"verify"},
  {title:"Compare the two executions", text:"Select Check execution traces. The honest scenario completes; the malformed-message scenario rejects without sending a message.", target:"run-trace", stage:"trace"},
  {title:"Keep the record", text:"Select Download evidence ZIP. You can inspect the logs here or reproduce this run later from the saved commands.", target:"bundle"}
];
const statusLabels = {CHECKED:"Model accepted", EXPORTED:"Lean files created", PROVED_UNDER_ASSUMPTIONS:"Checked under assumptions", PASSED:"Checks passed", TYPE_ERROR:"Type error", PARSE_ERROR:"JSON error", INTERNAL_ERROR:"Tool error", TRANSLATION_ERROR:"Translation error", OPEN_OBLIGATION:"Open obligation", CERTIFICATE_FAILED:"Certificate failed", SCENARIO_ERROR:"Scenario error", INCONCLUSIVE:"Inconclusive", NOT_CHECKED:"Not checked", NOT_RUN:"Not run", NOT_REPORTED:"Not reported", EXPECTED_REJECTION:"Expected rejection", NOT_CONFIRMED:"Not confirmed", queued:"Queued", running:"Running", completed:"Completed", failed:"Failed"};
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function json(value) { return JSON.stringify(value, null, 2); }
function badge(status) {
  const cls = ["CHECKED","EXPORTED","PROVED_UNDER_ASSUMPTIONS","PASSED","completed"].includes(status) ? "good" :
    ["TYPE_ERROR","PARSE_ERROR","INTERNAL_ERROR","TRANSLATION_ERROR","CERTIFICATE_FAILED","SCENARIO_ERROR","failed"].includes(status) ? "bad" :
    ["OPEN_OBLIGATION","INCONCLUSIVE"].includes(status) ? "warn" : "neutral";
  return '<span class="badge '+cls+'" title="'+esc(status)+'">'+esc(statusLabels[status] || status)+'</span>';
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw Error(value.error || response.statusText);
  return value;
}
function error(err) { $("error").hidden = false; $("error").textContent = err.message || String(err); }
function clearError() { $("error").hidden = true; }
function busy() { return run && ["queued","running"].includes(run.job.state); }
function stage(name) { return run?.stages.find(s => s.name === name); }
function link(row, download=false) { return "/api/runs/"+run.run_id+"/"+(download?"download":"files")+"/"+row.id; }
function rawLinks(name) {
  if (!run) return "";
  return run.artifacts.filter(a=>a.path==="stages/"+name+"/stdout.log" || a.path==="stages/"+name+"/stderr.log")
    .map(a=>'<a target="_blank" rel="noopener" href="'+link(a)+'">'+esc(a.path.split("/").pop())+'</a>').join(" · ");
}
function stageCard(name) {
  const s = stage(name);
  const prompts = {check:"Check the model to see its validation result.", export:"Create the Lean files to continue.", verify:"Run Lean to check the bindings and certificates.", trace:"Run the trace check to see the two execution scenarios.", controls:"Run this optional check to test altered bindings."};
  if (!s) return '<div class="card stage-card"><div class="status-row">'+badge(run?.job.stage===name?run.job.state:"NOT_RUN")+'</div><p>'+esc(prompts[name])+'</p></div>';
  const descriptions = {check:"The model was accepted by the syntax, type, and supported-operation checks.", export:"The generated representation is ready for Lean. No proof was checked during export.", verify:"The source/target bindings and named certificates were checked under the selected profile.", trace:"The honest and malformed-message executions were checked.", controls:"Both altered bindings were rejected at their expected checks."};
  const successful = ["CHECKED","EXPORTED","PROVED_UNDER_ASSUMPTIONS","PASSED"].includes(s.status);
  let note = successful ? descriptions[name] : (s.message || s.output?.message || s.output?.reason || "Inspect the recorded output for the diagnostic.");
  if (name==="check" && run.expected_check) note += s.meets_expected ? " This is the example's expected rejection." : " The expected rejection was not confirmed.";
  let html='<div class="card stage-card"><div class="status-row">'+badge(s.status);
  if(Number.isFinite(s.elapsed_ms)) html+='<span>'+esc((s.elapsed_ms/1000).toFixed(1))+' s</span>';
  html+='</div><p>'+esc(note)+'</p>';
  if(s.output?.signature_behavior_scope) html+='<p class="scope-note">'+esc(s.output.signature_behavior_scope)+'</p>';
  html+='<details><summary>Command result and raw output</summary><p class="note">Exit code '+esc(s.exit_code??"unavailable")+' · '+esc(s.started_at_utc||"")+' → '+esc(s.finished_at_utc||"")+'</p><pre class="preview">'+esc(json(s.output || s))+'</pre><p>'+rawLinks(name)+'</p></details></div>';
  return html;
}
function panels() {
  const r=run?.result || {};
  return '<div class="result-summary"><span>Model</span>'+badge(r.frontend_status||"NOT_CHECKED")+'<span>Lean</span>'+badge(r.certificate_status||"NOT_CHECKED")+'</div><p class="scope-note">These checks do not establish authentication, secrecy, or replay resistance.</p>';
}
function setPage(number) {
  page = Math.min(6,Math.max(1,number));
  localStorage.setItem("vake-page",String(page));
  document.querySelectorAll(".page").forEach((element,i)=>element.hidden=i+1!==page);
  document.querySelectorAll("#steps button").forEach((b,i)=>b.setAttribute("aria-current",i+1===page?"step":"false"));
  $("back").disabled=page===1;
  $("next").hidden=page===6;
  $("next").textContent=nextNames[page-1];
  $("page-number").textContent="Page "+page+" of 6";
  updateButtons();
}
function updateButtons() {
  $("run-check").disabled=!run||busy()||!!stage("check");
  $("run-export").disabled=!run||busy()||!!stage("export")||!["CHECKED","OPEN_OBLIGATION"].includes(stage("check")?.status);
  $("run-verify").disabled=!run||busy()||!!stage("verify")||stage("export")?.status!=="EXPORTED"||stage("check")?.status!=="CHECKED";
  for (const name of ["trace","controls"]) $("run-"+name).disabled=!run||busy()||!!stage(name)||stage("verify")?.status!=="PROVED_UNDER_ASSUMPTIONS"||!(name==="trace"?run.trace_eligible:run.terminal_demo_eligible);
  $("next").disabled=!run || (page===2 && !["CHECKED","OPEN_OBLIGATION"].includes(stage("check")?.status)) || (page===3 && stage("export")?.status!=="EXPORTED");
  $("bundle").classList.toggle("disabled",!run||busy());
  $("bundle").href=run?"/api/runs/"+run.run_id+"/bundle":"#";
  $("take-tour").disabled=!!busy();
  $("start-tour").disabled=!!busy();
  renderTour();
}
function render() {
  $("model-name").textContent=({"VAKE.NonceExchange":"Nonce exchange","VAKE.SignatureCheck":"Signature construction"}[run?.model_name]||run?.model_name)||"Choose a protocol to begin";
  $("welcome").hidden=!!run || tourActive;
  $("current-model").hidden=!run;
  $("run-id").textContent=run?run.run_id:"No active run";
  $("identity-hashes").innerHTML=run?'Model SHA-256 '+esc(run.source_sha256)+'<br>Profile SHA-256 '+esc(run.profile_sha256):"";
  $("job").textContent=(statusLabels[run?.job.state]||"Ready")+(busy()&&run.job.stage?" · "+names[{check:1,export:2,verify:3,trace:4,controls:4}[run.job.stage]]:"");
  $("schema").textContent=run?"Schema "+(run.schema||"unparsed"):"";
  $("check-result").innerHTML=stageCard("check");
  $("export-result").innerHTML=stageCard("export");
  $("verify-result").innerHTML=stageCard("verify");
  $("trace-stage").innerHTML=stageCard("trace");
  if(stage("trace") && stage("trace").status!=="PROVED_UNDER_ASSUMPTIONS") $("trace-output").open=true;
  $("controls-stage").innerHTML=stageCard("controls");
  renderTraces();
  $("controls-view").innerHTML=(run?.controls?.controls||[]).map(c=>'<p>'+badge(c.rejected_at_expected_binding?"EXPECTED_REJECTION":"NOT_CONFIRMED")+' '+esc(c.control)+' · Lean exit '+esc(c.exit_code)+'<br><code>'+esc(c.expected_failure)+'</code></p>').join("");
  const audit=displayAudit();
  $("verify-summary").innerHTML=audit?'<details class="card"><summary>Lean audit details</summary><p>'+esc(audit.lean_version)+'</p><div class="metrics"><div><strong>'+esc(audit.theorems.length)+'</strong><span>audited declarations</span></div><div><strong>'+esc(audit.axioms_used.length)+'</strong><span>logical axioms</span></div></div><p class="note">'+esc(audit.axioms_used.join(" · "))+'</p><p>'+esc(run.result.proof_scope)+'</p></details>':"";
  $("terminal-scope").textContent=run?.terminal_demo_eligible?
    "Exact bundled model + profile identified. This run checks the Announcer's initialized six-step local execution and stopped-session behavior. Check the separate honest and malformed global traces on Results. Security properties remain open.":
    "General correspondence route. The example-specific Announcer terminal certificate is disabled for this input/profile pair.";
  $("result-panels").innerHTML=panels();
  $("evidence-panels").innerHTML=panels();
  const selected=$("theorem").value;
  $("theorem").innerHTML=(audit?.theorems||[]).map((t,i)=>'<option value="'+i+'">'+esc(t.name)+'</option>').join("");
  if(selected) $("theorem").value=selected;
  $("audit-summary").textContent=audit?audit.theorems.length+" distinct declarations across this run’s completed audits. Logical axioms: "+audit.axioms_used.join(", ")+".":"No completed theorem audit in this run.";
  theoremDetail();
  $("stage-table").innerHTML='<table><thead><tr><th>Stage / UTC start</th><th>Status</th><th>Exit / expected</th><th>Elapsed</th></tr></thead><tbody>'+
    (run?.stages||[]).map(s=>'<tr><td>'+esc(s.name)+'<br>'+esc(s.started_at_utc||"—")+'</td><td>'+esc(s.status)+'</td><td>'+esc(s.exit_code??"—")+" / "+(s.meets_expected?"matched":"not matched")+'</td><td>'+esc(s.elapsed_ms??"—")+' ms</td></tr>').join("")+'</tbody></table>';
  const old=$("artifact-select").value;
  $("artifact-select").innerHTML=(run?.artifacts||[]).map(a=>'<option value="'+a.id+'">'+esc(a.path)+'</option>').join("");
  if(run?.artifacts.some(a=>a.id===old)) $("artifact-select").value=old;
  else if(run) {
    const preferred=run.artifacts.find(a=>a.path==="ui-result.json");
    if(preferred) $("artifact-select").value=preferred.id;
  }
  renderExport();
  const windows = run?.tool_versions?.python?.includes("MSC");
  $("reproduce").textContent=(run?.reproduce_commands||[]).map(command=>(windows?"& ":"")+command.map(arg=>shellQuote(arg,windows)).join(" ")).join("\n\n");
  $("versions").textContent=json(run?.tool_versions||{});
  $("missing").textContent="Missing evidence: "+json(run?.missing_evidence||[]);
  updateButtons();
}
function shellQuote(value, windows) {
  const clean=value.replaceAll("\\","/").replace("<PYTHON>","python");
  return "'" + clean.replaceAll("'",windows?"''":"'\"'\"'") + "'";
}
function theoremDetail() {
  const record=displayAudit()?.theorems[Number($("theorem").value)];
  $("theorem-detail").textContent=record?json(record):"No theorem selected.";
}
function renderExport() {
  const previous=$("export-artifact")?.value;
  const rows=(run?.artifacts||[]).filter(a=>(a.path.startsWith("export/")&&a.path.endsWith(".lean")&&(a.path.includes("/Generated/")||a.path.includes("/Imported/"))) || ["model.json","profile.json","export/export-manifest.json","export/source-map.json"].includes(a.path));
  if(!stage("export") || !rows.length) { $("export-files").textContent=""; return; }
  $("export-files").innerHTML='<div class="card"><label for="export-artifact">Generated Lean and source evidence</label><select id="export-artifact">'+rows.map(a=>'<option value="'+a.id+'">'+esc(a.path)+'</option>').join("")+'</select><div class="tools"><a id="export-download">Download</a><button id="export-copy" class="secondary small">Copy</button></div><div id="export-hash" class="hash"></div><pre id="export-text" class="preview"></pre></div>';
  const preferred=rows.find(a=>a.id===previous)||rows.find(a=>a.path.startsWith("export/VAKE/Generated/"))||rows[0];
  $("export-artifact").value=preferred.id;
  $("export-artifact").onchange=()=>loadExport().catch(error);
  $("export-copy").onclick=()=>navigator.clipboard.writeText(exportText).catch(error);
  loadExport().catch(error);
}
async function loadExport() {
  const row=run?.artifacts.find(a=>a.id===$("export-artifact")?.value);
  if(!row) return;
  const response=await fetch(link(row));
  exportText=await response.text();
  $("export-text").textContent=exportText;
  $("export-hash").textContent="SHA-256 "+row.sha256;
  $("export-download").href=link(row,true);
}
async function loadArtifact() {
  const row=run?.artifacts.find(a=>a.id===$("artifact-select").value);
  if(!row) return;
  const response=await fetch(link(row));
  artifactText=await response.text();
  $("artifact-hash").textContent="SHA-256 "+row.sha256+" · "+row.bytes+" bytes";
  $("raw").href=link(row);
  $("download").href=link(row,true);
  filterText();
}
function filterText() {
  const query=$("filter").value.toLowerCase();
  $("artifact-text").textContent=query?artifactText.split("\n").filter(line=>line.toLowerCase().includes(query)).join("\n"):artifactText;
}
async function refreshHistory() {
  const rows=await api("/api/runs");
  $("history").innerHTML=rows.filter(Boolean).map(row=>'<button class="history-item '+(run?.run_id===row.run_id?"active":"")+'" data-run="'+esc(row.run_id)+'">'+esc(row.model_name)+'<br>'+esc(row.run_id)+'<br>'+esc(row.job.state)+'</button>').join("");
  document.querySelectorAll("[data-run]").forEach(button=>button.onclick=()=>selectRun(button.dataset.run).catch(error));
}
async function selectRun(id) {
  clearError();
  run=await api("/api/runs/"+id);
  localStorage.setItem("vake-run",id);
  render();
  const model=run.artifacts.find(a=>a.path==="model.json");
  $("protocol-outline").textContent="Loading saved model…";
  $("model-preview").textContent=await (await fetch(link(model))).text();
  try {
    const model=JSON.parse($("model-preview").textContent);
    $("protocol-outline").innerHTML="<p><strong>Roles</strong></p><p>"+esc((model.roles||[]).map(r=>r.id).join(" · "))+"</p>";
  } catch (_) { $("protocol-outline").textContent="No JSON outline available."; }
  await loadArtifact();
  await refreshHistory();
  schedulePoll();
}
function schedulePoll() {
  clearTimeout(polling);
  if(busy()) polling=setTimeout(async()=>{
    try { await selectRun(run.run_id); } catch(err) { error(err); }
  },1500);
}
async function newRun(body, destination=1) {
  clearError();
  const created=await api("/api/runs",body);
  await selectRun(created.run_id);
  setPage(destination);
}
async function act(name) {
  if(!run) return;
  clearError();
  $("run-"+name).disabled=true;
  try { await api("/api/runs/"+run.run_id+"/"+name,{}); await selectRun(run.run_id); }
  catch(err) { error(err); updateButtons(); }
}
$("steps").innerHTML=names.map((name,i)=>'<button data-page="'+(i+1)+'">'+(i+1)+' · '+name+'</button>').join("");
document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>setPage(Number(b.dataset.page)));
$("back").onclick=()=>setPage(page-1);
$("next").onclick=()=>setPage(page+1);
$("run-check").onclick=()=>act("check");
$("run-export").onclick=()=>act("export");
$("run-verify").onclick=()=>act("verify");
$("run-trace").onclick=()=>act("trace");
$("run-controls").onclick=()=>act("controls");
$("load-example").onclick=()=>newRun({example:$("example").value}).catch(error);
$("negative").onclick=()=>newRun({example:"type_mismatch"},2).catch(error);
$("load-paste").onclick=()=>newRun({model:$("paste").value,...($("profile-text").value?{profile:$("profile-text").value}:{})}).catch(error);
$("upload").onchange=async()=>{
  try {
    const file=$("upload").files[0];
    if(!file) return;
    if(!file.name.toLowerCase().endsWith(".json")||file.size>2*1024*1024) throw Error("Choose a UTF-8 .json file no larger than 2 MiB");
    const text=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
    await newRun({model:text,...($("profile-text").value?{profile:$("profile-text").value}:{})});
  } catch(err) {error(err);}
};
$("artifact-select").onchange=()=>loadArtifact().catch(error);
$("theorem").onchange=theoremDetail;
$("filter").oninput=filterText;
$("copy").onclick=()=>navigator.clipboard.writeText(artifactText).catch(error);
$("refresh-history").onclick=()=>refreshHistory().catch(error);
(async()=>{
  examples=await api("/api/examples");
  $("example").innerHTML=examples.map(e=>'<option value="'+esc(e.id)+'">'+esc({nonce_exchange:"Nonce exchange — guided example",dh_exchange:"Diffie–Hellman exchange — honest and man-in-the-middle",signed_dh_exchange:"Signed Diffie–Hellman — substitutions rejected",type_mismatch:"Type mismatch — rejected input",signature_check:"Signature construction — limited example"}[e.id]||e.filename)+'</option>').join("");
  const remembered=localStorage.getItem("vake-run");
  if(remembered) {try {await selectRun(remembered);} catch(err){localStorage.removeItem("vake-run");error(err);}}
  if(!run) {render();await refreshHistory();}
  setPage(Number(localStorage.getItem("vake-page"))||1);
  if(window.location.hash==="#tour") { window.history.replaceState(null,"",window.location.pathname); await startTour(); }
})().catch(error);

function renderTraces() {
  const trace=run?.trace;
  if(!trace) { $("trace-view").textContent=""; return; }
  const cert=run.artifacts.find(a=>a.path==="traces/lean-check/VAKE/Demo/Global.lean");
  const audit=run.artifacts.find(a=>a.path==="traces/lean-check/validation/proof-audit.json");
  $("trace-view").innerHTML='<div class="scenario-grid">'+(trace.scenarios||[]).map(s=>'<section class="scenario"><h3>'+esc({honest:"Honest exchange",malformed:"Malformed message",mitm:"Man-in-the-middle",forged_share:"Forged share",spliced_signature:"Spliced signature"}[s.name]||s.name)+'</h3><p>'+esc(s.outcome)+'</p><p class="trace-stat">'+esc(s.events.length)+' checked actions · '+esc(s.send_count)+' sends</p><details><summary>Inspect checked steps</summary><p><code>'+esc(s.source_theorem)+'</code><br><code>'+esc(s.target_theorem)+'</code></p><table><thead><tr><th>Step</th><th>Session / action</th><th>Event / source location</th></tr></thead><tbody>'+s.events.map((e,i)=>'<tr><td>'+esc(i+1)+'</td><td>'+esc(e.session)+'<br>'+esc(s.actions[i])+'</td><td><strong>'+esc(e.kind)+'</strong> '+esc((e.names||[]).join(", "))+'<br><code>'+esc(e.location||"Network action")+'</code><details><summary>Values and certificate</summary><code>'+esc(s.theorem_prefix+"_step_"+(i+1))+'</code><pre>'+esc(json(e.values))+'</pre></details></td></tr>').join("")+'</tbody></table></details></section>').join("")+'</div><details><summary>Trace certificates and audit</summary><p>'+esc(trace.theorem_count)+' audited declarations, including shared theory. '+esc(trace.scope)+'</p><p>'+esc(trace.rendering_boundary)+'</p>'+(cert?'<a href="'+link(cert)+'" target="_blank" rel="noopener">Trace certificate</a> · ':"")+(audit?'<a href="'+link(audit)+'" target="_blank" rel="noopener">Statements and axiom audit</a>':"")+'</details>';
}
function displayAudit() {
  if(!run?.audit) return null;
  const audits=[run.audit,run.trace_audit].filter(Boolean);
  const records=new Map(audits.flatMap(a=>a.theorems).map(t=>[t.name,t]));
  return {...run.audit,theorems:[...records.values()],axioms_used:[...new Set(audits.flatMap(a=>a.axioms_used))].sort()};
}

function tourReady() {
  if(!run || busy()) return false;
  const required={2:["check","CHECKED"],3:["export","EXPORTED"],4:["verify","PROVED_UNDER_ASSUMPTIONS"],5:["trace","PROVED_UNDER_ASSUMPTIONS"]}[page];
  return !required || stage(required[0])?.status===required[1];
}
function renderTour() {
  $("tour-card").hidden=!tourActive;
  $("page-navigation").hidden=tourActive;
  document.querySelectorAll(".tour-highlight").forEach(e=>e.classList.remove("tour-highlight"));
  if(!tourActive) return;
  const step=tourSteps[page-1];
  $("tour-progress").textContent="Guided tour · "+page+" of 6";
  $("tour-title").textContent=step.title;
  $("tour-text").textContent=step.text;
  $("tour-next").textContent=page===6?"Finish tour":"Next step";
  $("tour-next").disabled=!tourReady();
  const current=step.stage?stage(step.stage):null;
  $("tour-state").textContent=busy()?"The check is running. You can inspect its result when it finishes.":tourReady()?(page===6?"Your run is saved. Download its evidence whenever you need it.":"Ready to continue."):current?"This stage did not pass. Inspect the diagnostic, or start a new tour to retry.":"Run the check above to continue.";
  $(step.target)?.classList.add("tour-highlight");
}
async function startTour() {
  if(busy()) return;
  await newRun({example:"nonce_exchange"},1);
  tourActive=true;
  localStorage.setItem("vake-tour","true");
  $("welcome").hidden=true;
  renderTour();
}
function endTour() {
  tourActive=false;
  localStorage.setItem("vake-tour","false");
  renderTour();
}
$("take-tour").onclick=()=>startTour().catch(error);
$("start-tour").onclick=()=>startTour().catch(error);
$("tour-close").onclick=endTour;
$("tour-next").onclick=()=>{
  if(!tourReady()) return;
  if(page===6) endTour();
  else {setPage(page+1);$(tourSteps[page-1].target)?.focus();}
};
