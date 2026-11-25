use super::*;
use crate::mirror_neuron::skills::{
    comparison_evidence, static_code_analysis, verification_checks,
};
use std::collections::BTreeSet;
use std::time::Instant;

pub const ROLES: [&str; 4] = ["functional", "security", "compatibility", "reliability"];
pub fn category(role: &str) -> Result<&'static str, String> {
    match role {
        "functional" => Ok("workflow"),
        "security" => Ok("boundary"),
        "compatibility" => Ok("policy"),
        "reliability" => Ok("test_control"),
        _ => Err("Unknown verifier role".into()),
    }
}
fn owner(kind: &str) -> Option<&'static str> {
    match kind {
        "syntax" | "schema_cases" | "test_oracles" | "literal_fields" | "test_changes" => {
            Some("functional")
        }
        "tls_defaults" | "guard_changes" | "security_inventory" | "workflow_permissions" => {
            Some("security")
        }
        "json_contract" | "package_entries" | "python_entry_points" | "public_interfaces" => {
            Some("compatibility")
        }
        "schema_workload" | "cleanup_errors" => Some("reliability"),
        _ => None,
    }
}
fn safe(p: &str) -> bool {
    !p.is_empty()
        && p.len() <= 512
        && !p.contains(['\\', ':'])
        && !p.chars().any(char::is_control)
        && p.split('/').all(|s| !matches!(s, "" | "." | ".."))
}
fn ident(s: &str) -> bool {
    s.len() <= 64
        && s.as_bytes().first().is_some_and(u8::is_ascii_alphabetic)
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}
fn test_path(p: &str) -> bool {
    let n = p.rsplit('/').next().unwrap_or(p);
    n.ends_with(".py") && (n.starts_with("test_") || n.ends_with("_test.py"))
}
pub fn sign(mut plan: Value) -> Value {
    plan.as_object_mut().unwrap().remove("plan_id");
    plan["plan_id"] = json!(hash(&plan.to_string()));
    plan
}
pub fn validate(plan: &Value, sources: &Value) -> Result<(), String> {
    if !plan.is_object()
        || sign(plan.clone())["plan_id"] != plan["plan_id"]
        || identity(sources)? != plan["subject"]
    {
        return Err("Frozen plan or source identity differs".into());
    }
    Ok(())
}
pub fn plan(run: &str, scope: &Value, c: &Value, role: Option<&str>) -> V {
    let sources = c["sources"].as_object().ok_or("Missing snapshot")?;
    let requested = scope["paths"].as_array().cloned().unwrap_or_default();
    if requested.iter().any(|p| !p.as_str().is_some_and(safe)) {
        return Err("Unsafe selected source path".into());
    }
    let paths: Vec<_> = sources
        .keys()
        .filter(|p| {
            requested.is_empty()
                || requested.iter().any(|v| {
                    v.as_str()
                        .is_some_and(|x| p.as_str() == x || p.starts_with(&format!("{x}/")))
                })
        })
        .collect();
    let mut blockers = Vec::new();
    if paths.is_empty() {
        blockers.push("No sources in selected scope".to_string())
    }
    for p in &requested {
        let p = p.as_str().unwrap();
        if !paths
            .iter()
            .any(|n| n.as_str() == p || n.starts_with(&format!("{p}/")))
        {
            blockers.push(format!("Requested path was not captured: {p}"))
        }
    }
    if scope
        .get("subject_sha256")
        .is_some_and(|s| s != &c["snapshot_id"])
    {
        blockers.push("Source differs from the approved subject digest".into())
    }
    let mut checks = Vec::new();
    let mut ids = BTreeSet::new();
    for check in scope["checks"].as_array().into_iter().flatten() {
        let mut check = check.clone();
        let id = string(&check, "id")?.to_owned();
        let kind = string(&check, "kind")?;
        if !ident(&id)
            || id.starts_with("auto-")
            || !ids.insert(id)
            || string(&check, "requirement")?.trim().is_empty()
        {
            return Err("Invalid approved check identity".into());
        }
        let who = if kind == "execution_record" {
            string(&check, "specialist")?
        } else {
            owner(kind).ok_or("Unknown check kind")?
        };
        category(who)?;
        if role.is_some_and(|r| r != who) || check.get("specialist").is_some_and(|r| r != who) {
            return Err("Check belongs to a different specialist".into());
        }
        if let Some(path) = check["file"].as_str() {
            if !safe(path) {
                return Err("Unsafe check file".into());
            }
            if !paths.iter().any(|p| p.as_str() == path) {
                blockers.push(format!("Required file outside selected scope: {path}"))
            }
        }
        check["specialist"] = json!(who);
        check["selection"] = json!("Required by the supervisor's scope");
        checks.push(check);
    }
    let py: Vec<_> = paths.iter().filter(|p| p.ends_with(".py")).collect();
    let text_has = |s: &str| {
        py.iter()
            .any(|p| sources[p.as_str()].as_str().is_some_and(|t| t.contains(s)))
    };
    for (kind, applies, requirement) in [
        (
            "syntax",
            !py.is_empty(),
            "Captured Python modules must parse.",
        ),
        (
            "test_oracles",
            py.iter().any(|p| test_path(p)),
            "Python tests must contain a meaningful assertion.",
        ),
        (
            "tls_defaults",
            ["requests", "ssl", "httpx", "urllib3"]
                .iter()
                .any(|v| text_has(v)),
            "TLS clients must retain certificate verification.",
        ),
        (
            "literal_fields",
            text_has("{"),
            "Distinct dictionary fields retain their values.",
        ),
        (
            "cleanup_errors",
            text_has("finally:"),
            "Cleanup preserves pending failures.",
        ),
        (
            "package_entries",
            paths
                .iter()
                .any(|p| p.rsplit('/').next() == Some("package.json")),
            "Declared local package entry files must exist.",
        ),
        (
            "workflow_permissions",
            paths.iter().any(|p| p.starts_with(".github/workflows/")),
            "Workflow permissions and action versions must be reviewable.",
        ),
        (
            "python_entry_points",
            paths.iter().any(|p| {
                p.ends_with("pyproject.toml")
                    && sources[p.as_str()].as_str().is_some_and(|s| {
                        s.contains("[project.scripts]") || s.contains("[project.gui-scripts]")
                    })
            }),
            "Declared Python entry points resolve in the captured distribution.",
        ),
        (
            "guard_changes",
            c["baseline"].is_object()
                && py.iter().any(|p| {
                    sources[p.as_str()]
                        .as_str()
                        .is_some_and(|s| s.contains("@"))
                }),
            "Preserve access checks across changed routes.",
        ),
        (
            "public_interfaces",
            !c["baseline"].is_null() && !py.is_empty(),
            "Preserve public interfaces across the source change.",
        ),
        (
            "test_changes",
            !c["baseline"].is_null() && py.iter().any(|p| test_path(p)),
            "Previously enabled tests remain effective.",
        ),
        (
            "security_inventory",
            paths
                .iter()
                .any(|p| p.ends_with("requirements.txt") || p.ends_with("pyproject.toml")),
            "Review dependencies in application context.",
        ),
    ] {
        let who = owner(kind).unwrap();
        if applies && role.is_none_or(|r| r == who) && !checks.iter().any(|c| c["kind"] == kind) {
            checks.push(json!({"id":format!("auto-{}",kind.replace('_',"-")),"kind":kind,"requirement":requirement,"specialist":who,"selection":"Applicable to the captured source"}))
        }
    }
    if role == Some("reliability")
        && !checks
            .iter()
            .any(|c| c["kind"] == "schema_workload" || c["kind"] == "execution_record")
    {
        blockers.push("A pinned workload or recovery observation is required.".into())
    }
    let decision = scope["decision"].as_str().unwrap_or("development");
    if decision != "development" {
        if role.is_some() {
            blockers.push("Merge and release decisions require the coordinator.".into())
        }
        for (k, side) in [("integrated_commit", "head"), ("base_commit", "base")] {
            if scope[k].is_null() || scope[k] != c["comparison"][side]["commit"] {
                blockers.push(format!("Missing matching immutable {k}"))
            }
        }
        if !scope["repository"].is_string()
            || scope["subject_sha256"] != c["snapshot_id"]
            || scope["targets"].as_array().is_none_or(|v| v.is_empty())
        {
            blockers.push(
                "Integration requires a repository, independent source digest and target matrix."
                    .into(),
            );
        }
        for target in scope["targets"].as_array().into_iter().flatten() {
            if !checks.iter().any(|v| {
                v["kind"] == "execution_record"
                    && v["specialist"] == "compatibility"
                    && &v["target"] == target
            }) {
                blockers.push(format!(
                    "Missing integrated compatibility record for {target}"
                ));
            }
        }
        if decision == "release"
            && (scope["artifact_sha256"].is_null()
                || c["verified_artifact"] != scope["artifact_sha256"])
        {
            blockers.push("Release artifact was not independently verified.".into());
        }
        if !requested.is_empty()
            || c["omitted"].as_array().is_some_and(|r| !r.is_empty())
            || c.pointer("/comparison/head/omitted")
                .and_then(Value::as_u64)
                .unwrap_or(0)
                > 0
        {
            blockers.push("A partial capture requires separate full-subject qualification.".into());
        }
        if !checks.iter().any(|c| c["kind"] == "execution_record") {
            blockers.push("Independent execution evidence required for integration.".into())
        }
    }
    let criteria: Vec<_> = scope["checks"]
        .as_array()
        .into_iter()
        .flatten()
        .cloned()
        .map(|mut v| {
            let m = v.as_object_mut().unwrap();
            m.remove("receipt_sha256");
            m.remove("baseline_receipt_sha256");
            v
        })
        .collect();
    let policy=hash(&json!({"decision":decision,"repository":scope["repository"],"base_commit":scope["base_commit"],
        "targets":scope["targets"].as_array().cloned().unwrap_or_default(),"specialist":role,"paths":requested,"checks":criteria}).to_string());
    let mut history = Vec::new();
    if let Some(pin) = scope["repair_of"].as_str() {
        let predecessor = (|| -> Result<Vec<Value>, String> {
            let old = evidence(pin)?;
            let report = old.get("specialist_report").unwrap_or(&old);
            let plan = &report["plan"];
            if !matches!(
                old["verdict"].as_str(),
                Some("FAIL" | "BLOCKED" | "INCONCLUSIVE")
            ) || !plan.is_object()
                || plan["schema_version"] != "mn.verification.v1.plan"
                || plan["policy_sha256"] != policy
                || sign(plan.clone())["plan_id"] != plan["plan_id"]
            {
                return Err(
                    "Repair requires a pinned nonpassing report under the same protected criteria"
                        .into(),
                );
            }
            let mut previous = list(plan, "repair_history")?.clone();
            if plan["subject"] == c["snapshot_id"]
                || previous.iter().any(|r| r["subject"] == c["snapshot_id"])
            {
                return Err("Repair requires a new candidate".into());
            }
            if previous.len() >= 2 {
                return Err("The two-candidate repair budget was exhausted".into());
            }
            let unmet: Vec<_> = list(report, "checks")?
                .iter()
                .filter(|v| v["status"] != "passed")
                .map(|v| &v["id"])
                .collect();
            previous.push(json!({"report_sha256":pin,"subject":plan["subject"],"run_id":plan["run_id"],"verdict":old["verdict"],"unmet":unmet}));
            Ok(previous)
        })();
        match predecessor {
            Ok(h) => history = h,
            Err(e) => blockers.push(e),
        }
    }
    let bs = if c["baseline"].is_object() {
        Some(identity(&c["baseline"])?)
    } else {
        None
    };
    Ok(sign(
        json!({"schema_version":"mn.verification.v1.plan","run_id":run,"subject":c["snapshot_id"],"baseline_subject":bs,
      "paths":paths,"scope_paths":requested,"checks":checks,"blockers":blockers,"decision":decision,"comparison":c["comparison"],
      "repository":scope["repository"],"base_commit":c["comparison"]["base"].get("commit").unwrap_or(&scope["base_commit"]),"revision":c["comparison"]["head"].get("commit").unwrap_or(&scope["integrated_commit"]),"base_artifact_sha256":scope["base_artifact_sha256"],"verified_base_artifact":c["verified_base_artifact"],"artifact_sha256":scope["artifact_sha256"],"verified_artifact":c["verified_artifact"],"targets":scope["targets"],"environment":{"runtime":"wasmtime","wasi":"0.3.0"},"policy_sha256":policy,"repair_history":history}),
    ))
}
pub fn evidence(pin: &str) -> V {
    if pin.len() != 64 || !pin.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("Invalid evidence digest".into());
    }
    let name = format!("runner-evidence/{pin}.json");
    let raw = match artifacts::read(&name, Some(pin)) {
        Ok(s) => s,
        Err(e) if e == "artifact_missing" => {
            let path = format!("/job/inputs/runner_evidence/{pin}.json");
            let file = std::fs::File::open(path).map_err(|_| "Pinned evidence is unavailable")?;
            let mut data = Vec::new();
            use std::io::Read;
            file.take(1_000_001)
                .read_to_end(&mut data)
                .map_err(|e| e.to_string())?;
            if data.len() > 1_000_000 {
                return Err("Pinned record exceeds its byte limit".into());
            }
            comparison_evidence::verify_file(&data, pin)?;
            let raw = String::from_utf8(data).map_err(|e| e.to_string())?;
            commit_text(&name, "json", &raw)?;
            raw
        }
        Err(e) => return Err(e),
    };
    parse(&verification_checks::strict_json(&raw)?)
}
pub fn stage_evidence(request: &Value, capture: &mut Value) -> Result<(), String> {
    let scope = selected_scope(&request["verification_scope"])?;
    for key in ["assurance_evidence_sha256", "assurance_basis_sha256"] {
        if let Some(pin) = request[key].as_str().filter(|s| !s.is_empty()) {
            evidence(pin)?;
        }
    }
    if let Some(pin) = scope["repair_of"].as_str() {
        match evidence(pin) {
            Ok(_) => (),
            Err(e) if e == "Pinned evidence is unavailable" => (),
            Err(e) => return Err(e),
        }
    }
    for check in scope["checks"].as_array().into_iter().flatten() {
        for key in [
            "receipt_sha256",
            "baseline_receipt_sha256",
            "test_inventory_sha256",
        ] {
            if let Some(pin) = check[key].as_str() {
                match evidence(pin) {
                    Ok(_) => (),
                    Err(msg) if msg == "Pinned evidence is unavailable" => (),
                    Err(msg) => return Err(msg),
                }
            }
        }
    }
    if scope["decision"] == "release" {
        for (key, verified) in [
            ("artifact_sha256", "verified_artifact"),
            ("base_artifact_sha256", "verified_base_artifact"),
        ] {
            let Some(pin) = scope[key].as_str() else {
                continue;
            };
            if pin.len() != 64 || !pin.bytes().all(|c| c.is_ascii_hexdigit()) {
                return Err("Invalid artifact digest".into());
            }
            use std::io::Read;
            let path = format!("/job/inputs/runner_evidence/{pin}.artifact");
            if let Ok(mut file) = std::fs::File::open(path) {
                let mut digest = Sha256::new();
                let mut bytes = 0usize;
                let mut buffer = [0; 65536];
                loop {
                    let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
                    if n == 0 {
                        break;
                    }
                    bytes += n;
                    if bytes > 512 * 1024 * 1024 {
                        return Err("Release artifact exceeds size budget".into());
                    }
                    digest.update(&buffer[..n]);
                }
                if format!("{:x}", digest.finalize()) != pin {
                    return Err("Release artifact differs from the approved digest".into());
                }
                capture[verified] = json!(pin);
            }
        }
    }
    Ok(())
}
pub fn observations(pin: Option<&str>, plan: &Value, sources: &Value) -> V {
    let Some(pin) = pin.filter(|s| !s.is_empty()) else {
        return Ok(json!({"digest":null,"cases":[],"coverage":null}));
    };
    let record = evidence(pin)?;
    if record["schema"] != "mn.comparison-evidence.v1"
        || record["subject"] != plan["subject"]
        || !record["baseline_subject"].is_null()
            && record["baseline_subject"] != plan["baseline_subject"]
    {
        return Err("Ledger differs from frozen revision".into());
    }
    let cases = list(&record, "cases")?;
    if cases.len() > 300 {
        return Err("Ledger exceeds case budget".into());
    }
    let mut ids = BTreeSet::new();
    for c in cases {
        let category = string(c, "category")?;
        let path = string(&c["source"], "path")?;
        let line = c["source"]["line"]
            .as_u64()
            .ok_or("Invalid evidence line")?;
        if !list(plan, "paths")?.iter().any(|p| p == path)
            || line == 0
            || sources[path]
                .as_str()
                .is_none_or(|text| line > text.lines().count() as u64)
        {
            return Err("Evidence cites a location outside the captured scope.".into());
        }
        let text = |v: &Value| {
            v.as_str()
                .is_some_and(|t| !t.trim().is_empty() && t.len() <= 1200)
        };
        if !text(&c["claim"])
            || !text(&c["expected"])
            || string(c, "fixture")?.len() != 64
            || !string(c, "fixture")?.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err("Incomplete protected observation".into());
        }
        if category == "policy"
            && (!matches!(c["expected"].as_str(), Some("allow" | "deny"))
                || ["actor", "action", "resource"]
                    .iter()
                    .any(|k| !text(&c["context"][*k])))
            || category == "test_control"
                && (c["expected"] != "killed"
                    || ["test", "change"].iter().any(|k| !text(&c["context"][*k])))
        {
            return Err("Invalid case expectation or context".into());
        }
        let mut run_ids = BTreeSet::new();
        for run in list(c, "runs")? {
            if !run_ids.insert(string(run, "id")?)
                || !run["clean"].is_boolean()
                || !text(&run["observed"])
                || !matches!(run["revision"].as_str(), Some("candidate" | "baseline"))
                || (run["revision"] == "baseline" && plan["baseline_subject"].is_null())
                || category == "policy"
                    && !matches!(run["observed"].as_str(), Some("allow" | "deny"))
                || category == "test_control"
                    && (!matches!(run["observed"].as_str(), Some("killed" | "survived"))
                        || !matches!(
                            run["original"].as_str(),
                            Some("passed" | "failed" | "unknown")
                        ))
            {
                return Err("Invalid protected observation run".into());
            }
        }
        if !ids.insert(string(c, "id")?)
            || !["workflow", "boundary", "policy", "test_control"].contains(&string(c, "category")?)
            || c.get("expected").is_none()
            || list(c, "runs")?.len() > 32
        {
            return Err("Invalid ledger case".into());
        }
    }
    Ok(json!({"digest":pin,"cases":cases,"coverage":record["coverage"]}))
}
pub fn select(ledger: &Value, role: &str) -> V {
    let category = category(role)?;
    Ok(
        json!({"digest":ledger["digest"],"coverage":if category=="test_control"{ledger["coverage"].clone()}else{Value::Null},
        "cases":list(ledger,"cases")?.iter().filter(|c|c["category"]==category).collect::<Vec<_>>() }),
    )
}
pub fn capture(run: &str, conf: &Value, p: &Value) -> V {
    let role = string(conf, "role")?;
    let managed = p["collaboration_group_id"]
        .as_str()
        .is_some_and(|s| !s.is_empty())
        && p["collaboration_peers"]
            .as_array()
            .is_some_and(|a| !a.is_empty());
    if managed {
        let row = match prior("collaboration/selected-assignment.json")? {
            Some(x) => x,
            None => {
                let mut filter = json!({"kind":"assignment","limit":1});
                if let Some(id) = conf["assignment_id"].as_str() {
                    filter["message_id"] = json!(id)
                }
                let row = mail_list(filter)?.into_iter().next().unwrap_or(Value::Null);
                commit("collaboration/selected-assignment.json", &row)?;
                row
            }
        };
        if let Some(id) = row["id"].as_str() {
            let v = attachment(id, "attachment")?;
            if conf["assignment_id"]
                .as_str()
                .is_some_and(|wanted| wanted != id)
            {
                return Err("Requested assignment was not returned".into());
            }
            if row["sender_blueprint_id"] != "software_verifier_suite"
                || v["schema"] != "software-verification.assignment.v1"
                || v["role"] != role
                || v["recipient_job_id"] != row["recipient_job_id"]
                || list(&v["plan"], "checks")?
                    .iter()
                    .any(|c| c["specialist"] != role)
            {
                return Err("Assignment scope mismatch".into());
            }
            validate(&v["plan"], &v["sources"])?;
            if v["plan"]["observation_scope"] != hash(&v["observations"].to_string())
                || list(&v["observations"], "cases")?
                    .iter()
                    .any(|c| c["category"] != category(role).unwrap_or(""))
            {
                return Err("Assignment observations differ".into());
            }
            for (pin, raw) in v["evidence_files"].as_object().into_iter().flatten() {
                if !list(&v["plan"], "checks")?.iter().any(|c| {
                    [
                        "receipt_sha256",
                        "baseline_receipt_sha256",
                        "test_inventory_sha256",
                    ]
                    .iter()
                    .any(|key| c[*key] == pin.as_str())
                }) {
                    return Err("Unassigned evidence in mailbox".into());
                }
                let bytes = raw.as_str().ok_or("Invalid evidence attachment")?;
                if bytes.len() > 256_000 || hash(bytes) != *pin {
                    return Err("Mailbox evidence digest differs".into());
                }
                commit_text(&format!("runner-evidence/{pin}.json"), "json", bytes)?;
            }
            return commit(
                "specialist-intake.json",
                &json!({"plan":v["plan"],"sources":v["sources"],"baseline":v["baseline"],"observations":v["observations"],"assignment":row}),
            );
        }
        if !std::path::Path::new("/job/inputs/software_sources").is_dir() {
            return commit("specialist-intake.json", &json!({"waiting":true}));
        }
    }
    if !std::path::Path::new("/job/inputs/software_sources").is_dir() {
        return Err("Choose a source folder for a standalone review or join Software verifier suite for assignments.".into());
    }
    let mut captured = subject(conf)?;
    stage_evidence(p, &mut captured)?;
    let plan = plan(
        run,
        &selected_scope(&p["verification_scope"])?,
        &captured,
        Some(role),
    )?;
    let ledger = observations(
        p["assurance_evidence_sha256"].as_str(),
        &plan,
        &captured["sources"],
    )?;
    commit(
        "specialist-intake.json",
        &json!({"plan":plan,"sources":captured["sources"],"baseline":captured["baseline"],"observations":select(&ledger,role)?}),
    )
}

fn observe(check: &Value, files: &Value, plan: &Value, baseline: &Value) -> V {
    let kind = string(check, "kind")?;
    let requirement = string(check, "requirement")?;
    if kind == "execution_record" {
        return super::receipts::check(check, plan, files, baseline);
    }
    let mut details = json!({});
    let mut refs = Vec::new();
    let mut findings = Vec::new();
    let mut executed = 0;
    let mut record = |path: &str, source: &str, line: u32, problem: Option<String>| {
        let evidence = json!({"path":path,"line":line,"sha256":hash(source)});
        if refs.len() < 128 && !refs.contains(&evidence) {
            refs.push(evidence.clone())
        }
        if let Some(observed) = problem {
            if findings.len() < 128 {
                findings.push(json!({"severity":"medium","expected":requirement,"observed":observed,"evidence":evidence,"reproduce":format!("Review {path} at line {line} against check {}.",check["id"]),"recommendation":requirement}));
            }
        }
    };
    match kind {
        "json_contract" | "schema_cases" | "schema_workload" => {
            let path = string(check, "file")?;
            let s = files[path]
                .as_str()
                .ok_or("Protected check input is absent")?;
            let mut passed;
            if kind == "json_contract" {
                passed = verification_checks::json_contract(s, &check["keys"].to_string())?;
                executed = 1;
            } else {
                if s.len() > 32_768 {
                    return Err("Schema exceeds its 32 KiB evaluation limit".into());
                }
                let cases = list(check, "cases")?;
                let seeds = check["cases"].to_string();
                let acceptance = check.get("acceptance_schema").map(Value::to_string);
                details = parse(&verification_checks::exercise_schema(
                    s,
                    &seeds,
                    acceptance.as_deref(),
                    kind == "schema_cases",
                )?)?;
                passed = details["passed"]
                    .as_bool()
                    .ok_or("Missing schema outcome")?;
                executed = list(&details, "examples")?.len();
                if kind == "schema_workload" {
                    let limit = check["max_p95_ms"]
                        .as_f64()
                        .filter(|v| *v > 0.0)
                        .ok_or("Invalid workload budget")?;
                    let mut samples = Vec::with_capacity(20);
                    for _ in 0..20 {
                        let start = Instant::now();
                        let measured = verification_checks::schema_cases(s, &seeds)?;
                        samples.push(start.elapsed().as_secs_f64() * 1000.0);
                        if parse(&measured)?
                            .as_array()
                            .is_none_or(|rows| rows.len() != cases.len())
                        {
                            return Err(
                                "Workload observation differs from the protected case inventory"
                                    .into(),
                            );
                        }
                    }
                    let mut sorted = samples.clone();
                    sorted.sort_by(f64::total_cmp);
                    let p95 = sorted[(sorted.len() * 95).div_ceil(100) - 1];
                    passed &= p95 <= limit;
                    details["samples_ms"] = json!(samples);
                    details["p95_ms"] = json!(p95);
                    details["max_p95_ms"] = json!(limit);
                }
            }
            record(
                path,
                s,
                1,
                (!passed)
                    .then(|| "Protected example, field value or workload budget differs.".into()),
            );
        }
        "syntax" | "tls_defaults" | "test_oracles" | "literal_fields" | "cleanup_errors" => {
            for pv in list(plan, "paths")? {
                let path = pv.as_str().ok_or("Invalid assigned path")?;
                if !path.ends_with(".py")
                    || kind == "test_oracles" && !test_path(path)
                    || kind == "tls_defaults" && test_path(path)
                {
                    continue;
                }
                let s = files[path].as_str().ok_or("Assigned source missing")?;
                let diags = if kind == "syntax" {
                    static_code_analysis::python_syntax(s)?
                } else {
                    static_code_analysis::python_check(kind, s)?
                };
                executed += 1;
                record(path, s, 1, None);
                for d in diags {
                    record(path, s, d.line, Some(d.message))
                }
            }
        }
        "public_interfaces" | "guard_changes" | "test_changes" => {
            let older = baseline
                .as_object()
                .ok_or("A pinned baseline is required for this comparison")?;
            let mut applicable = BTreeSet::new();
            for pv in list(plan, "paths")? {
                applicable.insert(pv.as_str().ok_or("Invalid source path")?);
            }
            for path in older.keys() {
                let selected = list(plan, "scope_paths")?;
                if selected.is_empty()
                    || selected.iter().any(|p| {
                        p.as_str()
                            .is_some_and(|s| path == s || path.starts_with(&format!("{s}/")))
                    })
                {
                    applicable.insert(path);
                }
            }
            for path in applicable {
                if !path.ends_with(".py") || (kind == "test_changes" && !test_path(path)) {
                    continue;
                }
                let base = older.get(path).and_then(Value::as_str).unwrap_or("");
                let head = files[path].as_str().unwrap_or("");
                let ds = static_code_analysis::compare_python(kind, base, head)?;
                let text = if head.is_empty() { base } else { head };
                executed += 1;
                record(path, text, 1, None);
                for issue in ds {
                    record(path, text, issue.line, Some(issue.message))
                }
            }
        }
        "workflow_permissions" | "security_inventory" | "python_entry_points" => {
            let mut notes = Vec::new();
            for item in list(plan, "paths")? {
                let path = item.as_str().ok_or("Invalid metadata path")?;
                let base = path.rsplit('/').next().unwrap_or(path);
                let applicable = match kind {
                    "workflow_permissions" => {
                        path.starts_with(".github/workflows/")
                            && (path.ends_with(".yaml") || path.ends_with(".yml"))
                    }
                    "python_entry_points" => base == "pyproject.toml",
                    _ => {
                        base == "pyproject.toml"
                            || base.starts_with("requirements") && base.ends_with(".txt")
                    }
                };
                if !applicable {
                    continue;
                }
                let text = files[path].as_str().ok_or("Missing manifest")?;
                let data = parse(&verification_checks::inspect_metadata(path, text)?)?;
                if kind == "workflow_permissions" {
                    executed += 1;
                    record(path, text, 1, None);
                    for note in list(&data, "review")? {
                        notes.push(
                            note.as_str()
                                .ok_or("Invalid workflow observation")?
                                .to_owned(),
                        );
                    }
                } else if kind == "security_inventory" {
                    for dep in list(&data, "dependencies")? {
                        executed += 1;
                        let value = dep.as_str().ok_or("Invalid dependency")?;
                        if !value.contains("==") || value.contains('*') || value.starts_with('-') {
                            notes.push(format!(
                                "{path}: dependency requires independent qualification: {value}"
                            ));
                        }
                    }
                    record(path, text, 1, None);
                } else {
                    for (name, target) in
                        data["entries"].as_object().ok_or("Invalid entry points")?
                    {
                        let (module, symbol) = target
                            .as_str()
                            .and_then(|t| t.split_once(':'))
                            .ok_or("Invalid Python entry point")?;
                        if module.split('.').chain(symbol.split('.')).any(|s| {
                            s.is_empty() || !s.chars().all(|c| c.is_alphanumeric() || c == '_')
                        }) {
                            return Err("Invalid module or symbol".into());
                        }
                        executed += 1;
                        let parent = path.strip_suffix("pyproject.toml").unwrap_or("");
                        let module = module.replace('.', "/");
                        let targets = [
                            format!("{parent}{module}.py"),
                            format!("{parent}{module}/__init__.py"),
                            format!("{parent}src/{module}.py"),
                            format!("{parent}src/{module}/__init__.py"),
                        ];
                        let src = targets.iter().find_map(|f| files[f].as_str());
                        let ok = match src {
                            Some(src) => static_code_analysis::python_callables(src)?
                                .iter()
                                .any(|s| s == symbol),
                            None => false,
                        };
                        record(
                            path,
                            text,
                            1,
                            (!ok).then(|| {
                                format!("Entry point {name} references a missing callable.")
                            }),
                        );
                    }
                }
            }
            if !notes.is_empty() {
                return Err(notes.into_iter().take(10).collect::<Vec<_>>().join(" | "));
            }
        }
        "package_entries" => {
            for pv in list(plan, "paths")? {
                let path = pv.as_str().ok_or("Invalid package path")?;
                if path.rsplit('/').next() != Some("package.json") {
                    continue;
                }
                let text = files[path].as_str().ok_or("Missing package")?;
                let pkg = parse(text)?;
                let mut entries = Vec::new();
                for key in ["main", "module", "types", "typings", "bin", "exports"] {
                    if let Some(v) = pkg.get(key) {
                        local_entries(v, &mut entries)
                    }
                }
                let parent = path.rsplit_once('/').map_or("", |(p, _)| p);
                for file in entries {
                    let file = file.trim_start_matches("./");
                    if !safe(file) || file.contains('*') {
                        return Err("Package target needs a concrete local file".into());
                    }
                    let target = if parent.is_empty() {
                        file.to_owned()
                    } else {
                        format!("{parent}/{file}")
                    };
                    executed += 1;
                    record(
                        path,
                        text,
                        1,
                        files
                            .get(&target)
                            .is_none()
                            .then(|| format!("Missing declared package target {target}")),
                    );
                }
            }
        }
        _ => {
            return Err(format!(
                "The {kind} check has no qualifying observation on this runner."
            ));
        }
    }
    if executed == 0 {
        return Err("No applicable source or protected example was available.".into());
    }
    let mut row = json!({"status":if findings.is_empty(){"passed"}else{"failed"},"executed":executed,"evidence":refs,"findings":findings,
        "observed":"Checked the captured source and protected expectations."});
    details.as_object_mut().unwrap().remove("passed");
    row.as_object_mut()
        .unwrap()
        .extend(details.as_object().unwrap().clone());
    Ok(row)
}
fn local_entries<'a>(v: &'a Value, out: &mut Vec<&'a str>) {
    match v {
        Value::String(s) => out.push(s),
        Value::Array(a) => a.iter().for_each(|v| local_entries(v, out)),
        Value::Object(m) => m.values().for_each(|v| local_entries(v, out)),
        _ => {}
    }
}
pub fn attempts(
    plan: &Value,
    files: &Value,
    baseline: &Value,
    role: &str,
) -> Result<Vec<Value>, String> {
    validate(plan, files)?;
    if !plan["baseline_subject"].is_null() && identity(baseline)? != plan["baseline_subject"] {
        return Err("Baseline identity differs".into());
    }
    let mut result = vec![];
    for c in list(plan, "checks")?
        .iter()
        .filter(|c| c["specialist"] == role)
    {
        progress("Checking captured evidence");
        let id = string(c, "id")?;
        if !ident(id) {
            return Err("Invalid check identity".into());
        }
        let path = format!(
            "verification-attempts/{}/{id}-1.json",
            string(plan, "plan_id")?
        );
        if let Some(r) = prior(&path)? {
            result.push(r);
            continue;
        }
        let mut row = observe(c, files, plan, baseline).unwrap_or_else(|e| {
            json!({"status":if e=="Pinned evidence is unavailable"{"blocked"}else{"inconclusive"},
            "observed":e,"executed":0,"evidence":[],"findings":[]})
        });
        let identity = json!({"schema_version":"mn.verification.v1.result","run_id":plan["run_id"],"subject":plan["subject"],"plan_id":plan["plan_id"],
            "specialist":role,"check_id":id,"attempt":1,"retryable":false});
        row.as_object_mut()
            .unwrap()
            .extend(identity.as_object().unwrap().clone());
        if baseline.is_object() && c["kind"] != "execution_record" {
            let prior = observe(c, baseline, plan, baseline)
                .unwrap_or_else(|e| json!({"status":"inconclusive","observed":e}));
            let status = string(&row, "status")?;
            let pair = parse(&comparison_evidence::compare(
                &json!("passed").to_string(),
                Some(&prior["status"].to_string()),
                Some(&json!(status).to_string()),
            )?)?;
            row["comparison"] = json!({"classification":pair["change"],"baseline":prior,"candidate":{"status":status}});
        }
        commit(&path, &row)?;
        result.push(row);
    }
    Ok(result)
}
pub fn rollup(plan: &Value, records: &[Value]) -> V {
    let mut unsigned = plan.clone();
    unsigned
        .as_object_mut()
        .ok_or("Invalid frozen plan")?
        .remove("plan_id");
    parse(&verification_checks::reconcile(
        &json!({"plan_id":plan["plan_id"],"canonical":unsigned.to_string()}).to_string(),
        &json!(records).to_string(),
    )?)
}
pub fn with_aspect(mut report: Value, selected: &Value) -> V {
    let a = parse(&comparison_evidence::assess(&selected.to_string())?)?;
    let cases = list(&a, "cases")?;
    if cases.iter().any(|v| v["status"] == "unmet") {
        report["verdict"] = json!("FAIL")
    } else if report["verdict"] == "PASS" && cases.iter().any(|v| v["status"] != "met") {
        report["verdict"] = json!("INCONCLUSIVE")
    };
    report["aspect"] = a;
    Ok(report)
}
pub fn document(report: &Value, title: &str) -> Value {
    let blocks=report["checks"].as_array().into_iter().flatten().map(|c|json!({"type":"paragraph","text":format!("{} · {} · {}",c["id"].as_str().unwrap_or(""),c["status"].as_str().unwrap_or(""),c["reason"].as_str().unwrap_or(""))})).collect::<Vec<_>>();
    json!({"title":title,"identity":report["plan"]["run_id"],"summary":report["verdict"],"sections":[{"title":"Verification checks","blocks":blocks}]})
}
pub fn evaluate(_run: &str, conf: &Value, previous: &Value) -> V {
    let p = read(previous)?;
    let role = string(conf, "role")?;
    let mut reply = Value::Null;
    let report = if p["waiting"] == true {
        json!({"schema_version":"mn.verification.v1.report","status":"waiting_for_assignment","verdict":"INCONCLUSIVE","plan":null,"checks":[],"findings":[],"blockers":[]})
    } else {
        let plan = &p["plan"];
        let records = attempts(plan, &p["sources"], &p["baseline"], role)?;
        let report = with_aspect(rollup(plan, &records)?, &p["observations"])?;
        if let Some(id) = p["assignment"]["id"].as_str() {
            reply = json!({"message":{"recipient_job_id":p["assignment"]["sender_job_id"],"kind":"result","request_id":id,"reply_to":id,"subject":format!("{role} verification"),"text":string(&report,"verdict")?},
                "attachment":{"assignment_id":id,"plan":plan,"records":records,"aspect":report["aspect"]}});
        }
        report
    };
    let title = if p["waiting"] == true {
        "Waiting for an assignment".to_string()
    } else {
        format!("{role} verification")
    };
    commit(
        "specialist-review.json",
        &json!({"data":report,"document":document(&report,&title),"reply":reply}),
    )
}

pub fn publish_report(reference: &Value) -> V {
    let packet = read(reference)?;
    let receipt = publish(&packet["data"], &packet["document"])?;
    if let Some(message) = packet["reply"].get("message") {
        mail_send(message.clone(), &packet["reply"]["attachment"])?;
        mailbox::acknowledge(string(message, "reply_to")?)?;
    }
    Ok(receipt)
}
