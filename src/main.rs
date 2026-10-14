use serde_json::{Value, json};
use std::{env, fs, path::{Path, PathBuf}, process::{self, Command}, time::{SystemTime, UNIX_EPOCH}};

type Failure = (String, String);
fn failure(status: &str, message: impl Into<String>) -> Failure { (status.into(), message.into()) }
fn read(path: &Path) -> Result<Vec<u8>, Failure> { fs::read(path).map_err(|e| failure("INTERNAL_ERROR", format!("{}: {e}", path.display()))) }
fn checked(bytes: &[u8]) -> Result<Value, Failure> {
    let model = vake::parse_model(bytes).map_err(|e| failure("PARSE_ERROR", e))?;
    let report = vake::check::check(&model).map_err(|e| failure("TYPE_ERROR", e))?;
    vake::contracts::contracts(&model).map_err(|e| failure("UNSUPPORTED", e))?;
    Ok(json!({"status":if report.closed {"CHECKED"} else {"OPEN_OBLIGATION"},"parse_status":"OK","type_status":"OK","backend_status":"SUPPORTED","proof_status":"NOT_CHECKED","kernel":report}))
}
fn project_root() -> Result<PathBuf, Failure> {
    if let Some(root) = env::var_os("VAKE_ROOT") {
        let root = PathBuf::from(root);
        if root.join("scripts/verify.py").is_file() { return Ok(root); }
        return Err(failure("INTERNAL_ERROR", "VAKE_ROOT must point to the extracted repository"));
    }
    if let Ok(exe) = env::current_exe() {
        for p in exe.ancestors().skip(1) {
            if p.join("scripts/verify.py").is_file() && p.join("Cargo.toml").is_file() { return Ok(p.to_path_buf()); }
        }
    }
    Err(failure("INTERNAL_ERROR", "Cannot locate the installed VAKE data; set VAKE_ROOT to the repository root"))
}
fn python(root: &Path, script: &str, args: &[String]) -> Result<i32, Failure> {
    let configured = env::var_os("VAKE_PYTHON");
    let candidates: Vec<std::ffi::OsString> = configured.map(|p| vec![p]).unwrap_or_else(|| vec!["python3".into(), "python".into()]);
    for candidate in candidates {
        if Command::new(&candidate).arg("--version").output().is_ok_and(|o| o.status.success()) {
            let status = Command::new(candidate).arg(root.join("scripts").join(script)).args(args).status()
                .map_err(|e| failure("INTERNAL_ERROR", format!("Python launch failed: {e}")))?;
            return Ok(status.code().unwrap_or(1));
        }
    }
    Err(failure("INTERNAL_ERROR", "Python 3 is required for independent import and verification; set VAKE_PYTHON"))
}
fn execute() -> Result<i32, Failure> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() || ["--help", "-h", "help"].contains(&args[0].as_str()) {
        println!("VAKE: typed JSON DSL and Lean 4 correspondence checking\n\nvake check MODEL.json\nvake export MODEL.json --profile PROFILE.json --out DIRECTORY\nvake verify MODEL.json --profile PROFILE.json [--out DIRECTORY]\nvake demo\n\nCHECKED and LEAN_COMPILED do not imply protocol security. Verify checks source/target binding and correspondence. Authentication and secrecy remain open.");
        return Ok(0);
    }
    if args[0] == "--version" { println!("VAKE {}", env!("CARGO_PKG_VERSION")); return Ok(0); }
    if args[0] == "demo" && args.len() == 1 { return python(&project_root()?, "demo.py", &[]); }
    if !["check", "export", "verify"].contains(&args[0].as_str()) || args.len() < 2 { return Err(failure("INTERNAL_ERROR", "Unknown command or missing model; use --help")); }
    let bytes = read(Path::new(&args[1]))?;
    let admission = checked(&bytes)?;
    if args[0] == "check" {
        if args.len() != 2 { return Err(failure("INTERNAL_ERROR", "check expects exactly one model path")); }
        println!("{}", serde_json::to_string_pretty(&admission).unwrap());
        return Ok(if admission["status"] == "OPEN_OBLIGATION" {2} else {0});
    }
    let mut profile = None;
    let mut out = None;
    let mut options = args[2..].chunks_exact(2);
    for pair in &mut options {
        match pair[0].as_str() {
            "--profile" if profile.is_none() => profile = Some(PathBuf::from(&pair[1])),
            "--out" if out.is_none() => out = Some(PathBuf::from(&pair[1])),
            _ => return Err(failure("INTERNAL_ERROR", "Unknown or duplicate option; use --help")),
        }
    }
    if !options.remainder().is_empty() { return Err(failure("INTERNAL_ERROR", "An option value is missing")); }
    let profile = profile.ok_or_else(|| failure("UNSUPPORTED", "An explicit --profile is required for export or verify"))?;
    let profile_bytes = read(&profile)?;
    vake::transport::unique(&profile_bytes).map_err(|e| failure("PARSE_ERROR", format!("profile: {e}")))?;
    let profile_value: Value = serde_json::from_slice(&profile_bytes).map_err(|e| failure("PARSE_ERROR", format!("profile: {e}")))?;
    if profile_value["schema_version"] != "1.0" || profile_value["interpretation"] != "restricted_symbolic_v1" {
        return Err(failure("UNSUPPORTED", "Only the restricted_symbolic_v1 schema 1.0 operational profile is supported"));
    }
    let output = if let Some(p) = out {p} else if args[0] == "verify" {
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        project_root()?.join("reports/runs").join(format!("verify-{stamp}"))
    } else { return Err(failure("INTERNAL_ERROR", "export requires --out DIRECTORY")); };
    let manifest = vake::lean_export::export(&bytes, &profile_bytes, &output).map_err(|e| failure("TRANSLATION_ERROR", e))?;
    if args[0] == "export" {
        println!("{}", serde_json::to_string_pretty(&json!({"status":"EXPORTED","proof_status":"NOT_CHECKED","module":manifest["module"],"output":output})).unwrap());
        return Ok(0);
    }
    if admission["status"] == "OPEN_OBLIGATION" {
        println!("{}", json!({"status":"OPEN_OBLIGATION","reason":"Model contains holes; export saved but verification cannot report a closed model","output":output}));
        return Ok(2);
    }
    let root = project_root()?;
    let absolute = fs::canonicalize(&output).map_err(|e| failure("INTERNAL_ERROR", e.to_string()))?;
    python(&root, "verify.py", &["--export-dir".into(), absolute.to_string_lossy().into_owned()])
}
fn main() {
    let code = match execute() {
        Ok(code) => code,
        Err((status, message)) => { println!("{}", json!({"status":status,"message":message,"security_conclusion":"none"})); 1 }
    };
    process::exit(code);
}

