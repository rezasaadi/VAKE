from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
def main():
    output=ROOT/"reports/ci-evidence"
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    allowed={"preflight-result.json","reproduction-result.json","demo-result.json","verification-result.json","trace-result.json","proof-audit.json","negative-binding-results.json","signature-observations.json"}
    for path in sorted((ROOT/"reports/runs").rglob("*")):
        if not path.is_file() or ".lake" in path.parts or path.suffix!=".log" and path.name not in allowed: continue
        rel=path.relative_to(ROOT/"reports/runs")
        original=path.read_bytes()
        text=original.decode("utf-8",errors="replace").replace(str(ROOT),"<REPO>").replace(str(ROOT).replace("\\","/"),"<REPO>")
        text=text.replace(str(ROOT).replace("\\","\\\\"),"<REPO>")
        text=re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+","<HOME>",text)
        text=re.sub(r"/(?:home|Users)/[^/\s\"']+","<HOME>",text)
        data=text.encode("utf-8")
        target=output/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        rows.append({"path":rel.as_posix(),"original_sha256":hashlib.sha256(original).hexdigest(),"sha256":hashlib.sha256(data).hexdigest()})
    (output/"manifest.json").write_text(json.dumps({"scope":"Normalized copies of execution logs and result metadata, not a source archive","files":rows},indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()

