use super::specialist::*;
use super::*;
use crate::mirror_neuron::run::{approvals, model};
use crate::mirror_neuron::skills::{code_search, static_code_analysis};
use std::collections::{BTreeMap, BTreeSet};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
fn ask(phase: &str, packet: &Value) -> V {
    let (prompt, schema) = match phase {
        "extract" => (
            include_str!("../../../software_verifier_suite/payloads/prompts/extract.md"),
            include_str!("../../schemas/extract.json"),
        ),
        "verify" => (
            include_str!("../../../software_verifier_suite/payloads/prompts/verify.md"),
            include_str!("../../schemas/verify.json"),
        ),
        "judge" => (
            include_str!("../../../software_verifier_suite/payloads/prompts/judge.md"),
            include_str!("../../schemas/judge.json"),
        ),
        "critique" => (
            include_str!("../../../software_verifier_suite/payloads/prompts/critique.md"),
            include_str!("../../schemas/critique.json"),
        ),
        _ => return Err("Unknown model operation".into()),
    };
    let input = packet.to_string();
    if input.len() > 100000 {
        return Err("Model evidence packet exceeds its budget".into());
    }
    progress("Requesting structured model evidence");
    parse(&model::generate_json(prompt, &input, schema)?)
}
fn capture(conf: &Value, p: &Value) -> V {
    let mut c = subject(conf)?;
    stage_evidence(p, &mut c)?;
    let source = c["sources"].as_object().ok_or("Missing captured text")?;
    let review = &conf["review"];
    let spec_paths = review["spec_paths"]
        .as_str()
        .unwrap_or("")
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect::<BTreeSet<_>>();
    if spec_paths.len() > 100 || spec_paths.iter().any(|p| !source.contains_key(*p)) {
        return Err("A selected specification was not captured".into());
    }
    let doc_scope = review["documentation_scope"]
        .as_str()
        .unwrap_or("current_requirements");
    if !matches!(
        doc_scope,
        "current_requirements" | "all_captured_docs" | "project_docs"
    ) {
        return Err("Invalid document scope".into());
    }
    let mut docs = vec![];
    let mut publication = Vec::new();
    let mut analysis = BTreeMap::new();
    for (path, t) in source {
        let s = t.as_str().ok_or("Missing source text")?;
        if path.starts_with('.') && !path.starts_with(".github/") {
            continue;
        }
        publication.push(commit_text(&format!("source/{path}"), "source", s)?);
        if [".md", ".rst", ".txt", ".adoc"]
            .iter()
            .any(|e| path.to_lowercase().ends_with(e))
        {
            let name = path.rsplit('/').next().unwrap_or(path).to_lowercase();
            let historical = ["history", "changelog", "changes", "release-notes"]
                .iter()
                .any(|p| name.starts_with(p))
                || path.split('/').any(|p| {
                    matches!(
                        p,
                        "archive" | "archives" | "evaluations" | "evaluation-results"
                    )
                });
            if (!spec_paths.is_empty() && spec_paths.contains(path.as_str()))
                || (spec_paths.is_empty() && (doc_scope != "current_requirements" || !historical))
            {
                docs.push(path.clone());
            }
        }
        if path.ends_with(".py") {
            let syntax = static_code_analysis::python_syntax(s)?;
            analysis.insert(path,json!({"valid":syntax.is_empty(),"imports":static_code_analysis::python_imports(s).unwrap_or_default()}));
        }
    }
    if let Some(base) = c["baseline"].as_object() {
        for (path, text) in base {
            publication.push(commit_text(
                &format!("baseline/{path}"),
                "source",
                text.as_str().ok_or("Invalid baseline")?,
            )?);
        }
    }
    commit("publication-inputs.json", &json!(publication))?;
    let static_ref = commit("static-analysis.json", &json!(analysis))?;
    c["schema_version"] = json!("mn.software_rules.capture.v1");
    c["source_execution"] = json!(false);
    c["documents"] = json!(docs);
    c["review_settings"] = review.clone();
    c["request"] = p.clone();
    let source_ref = commit("capture.json", &c)?;
    Ok(json!({"capture":source_ref,"static_analysis":static_ref,"snapshot_id":c["snapshot_id"]}))
}
fn extract(previous: &Value, conf: &Value) -> V {
    if let Some(packet) = prior("extraction-output.json")? {
        return Ok(packet);
    }
    let c = read(&previous["capture"])?;
    let mut rules = Vec::new();
    let mut gaps = Vec::new();
    let mut packets = 0;
    let mut seen = BTreeSet::new();
    let policy = &c["review_settings"];
    let deadline = policy["extraction_timeout_seconds"]
        .as_u64()
        .map(|s| now() + s * 1000);
    let instructions = c["request"]["supervisor_instructions"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    for (index, text) in instructions.iter().enumerate() {
        let text = if let Some(s) = text.as_str() {
            s
        } else {
            text["statement"]
                .as_str()
                .ok_or("Invalid supervisor instruction")?
        };
        if text.trim().is_empty() || text.len() > 4000 {
            return Err("Invalid supervisor rule".into());
        }
        rules.push(json!({"id":format!("supervisor-{}",&hash(text)[..16]),"statement":text,"title":text.chars().take(90).collect::<String>(),
            "origin":"supervisor","source":{"path":"supervisor","start_line":index+1,"end_line":index+1,"quote":text}}));
    }
    for path in list(&c, "documents")? {
        if !instructions.is_empty() && policy["rules_mode"] == "replace" {
            break;
        }
        let path = path.as_str().ok_or("Invalid documentation path")?;
        let body = c["sources"][path].as_str().ok_or("Missing document")?;
        let lines: Vec<_> = body.lines().collect();
        for (page, window) in lines.chunks(48).enumerate() {
            let start = page * 48;
            packets += 1;
            if packets
                > policy["max_extraction_packets"]
                    .as_u64()
                    .unwrap_or(512)
                    .min(2048)
                || deadline.is_some_and(|d| now() >= d)
            {
                gaps.push(json!({"path":path,"start_line":start+1,"reason":"Configured extraction budget reached."}));
                break;
            }
            let refs: Vec<_> = window
                .iter()
                .enumerate()
                .map(
                    |(i, line)| json!({"id":format!("L{}",start+i+1),"line":start+i+1,"text":line}),
                )
                .collect();
            let packet = json!({"path":path,"numbered_lines":refs,"snapshot_id":c["snapshot_id"]});
            let cache = format!("extraction/{}.json", hash(&packet.to_string()));
            let response = match prior(&cache)? {
                Some(r) => r,
                None => {
                    let r = if conf["simulated_model"] == true {
                        // Give the SDK simulator a legal source ID. The live extraction schema is untouched.
                        let mut schema = parse(include_str!("../../schemas/extract.json"))?;
                        let sample = json!({"complete":true,"rules":[{"statement":"Simulated rule for execution timing.",
                            "source_ids":[refs[0]["id"]],"subject":"timing fixture","scope":"sample",
                            "modality":"descriptive","conditions":[],"requirement_kind":"behavior"}]});
                        schema["examples"] = json!([sample]);
                        parse(&model::generate_json(
                            "Generate a structural sample.",
                            &packet.to_string(),
                            &schema.to_string(),
                        )?)?
                    } else {
                        ask("extract", &packet)?
                    };
                    commit(&cache, &r)?;
                    r
                }
            };
            if response["complete"] != true {
                gaps.push(json!({"path":path,"start_line":start+1,"reason":"The model did not finish this packet."}));
            }
            for v in list(&response, "rules")? {
                let mut row = v.clone();
                let mut line_numbers = vec![];
                for id in list(v, "source_ids")? {
                    let n = refs
                        .iter()
                        .find(|r| r["id"] == *id)
                        .and_then(|r| r["line"].as_u64())
                        .ok_or("Rule cites an unobserved source line")?;
                    line_numbers.push(n as usize);
                }
                line_numbers.sort();
                let first = *line_numbers.first().ok_or("Missing rule source")?;
                let last = *line_numbers.last().unwrap();
                let statement = string(v, "statement")?;
                let id = format!(
                    "rule-{}",
                    &hash(&json!([path, line_numbers, statement]).to_string())[..16]
                );
                if !seen.insert(id.clone()) {
                    continue;
                }
                row["id"] = json!(id);
                row["source"] = json!({"path":path,"start_line":first,"end_line":last,"quote":lines[first-1..last].join("\n")});
                row["origin"] = json!("documentation");
                rules.push(row);
                if rules.len() > policy["max_rules"].as_u64().unwrap_or(2000).min(2000) as usize {
                    return Err("Extracted rule limit exceeded".into());
                }
            }
            if packets > 2048 {
                return Err("Document packet limit exceeded".into());
            }
        }
    }
    if rules.is_empty() {
        return Err("No source-backed software rules were extracted".into());
    }
    let bundle = json!({"schema_version":"mn.software_rules.rules.v1","snapshot_id":c["snapshot_id"],"rules":rules,"extraction_gaps":gaps});
    let rules_ref = commit("rules.json", &bundle)?;
    let md = rules
        .iter()
        .map(|r| format!("- {}", r["statement"].as_str().unwrap_or("")))
        .collect::<Vec<_>>()
        .join("\n");
    commit_text("rules.md", "markdown", &md)?;
    commit(
        "extraction-status.json",
        &json!({"packets":packets,"rules":rules.len(),"gaps":gaps}),
    )?;
    let out =
        json!({"capture":previous["capture"],"rules":rules_ref,"snapshot_id":c["snapshot_id"]});
    commit("extraction-output.json", &out)?;
    Ok(out)
}
fn request(rules: &Value, rev: u64, expiry: u64) -> V {
    let digest = hash(&rules.to_string());
    let entries = list(rules, "rules")?;
    let items=entries.iter().map(|r|json!({"id":r["id"],"title":r["title"].as_str().unwrap_or_else(||r["statement"].as_str().unwrap_or("Software rule")).chars().take(90).collect::<String>(),
        "markdown":r["statement"],"context":format!("Source {} lines {}–{}",r["source"]["path"],r["source"]["start_line"],r["source"]["end_line"])})).collect::<Vec<_>>();
    let doc = json!({"schema":"mn.markdown-review.v1","title":"Review software rules","items":items,"instructions":"Review the captured rules. Save edits before approving the complete revision."});
    let bytes = format!("{doc}\n");
    let path = format!("reviews/rules-{}.json", hash(&bytes));
    let file = commit_text(&path, "markdown_review", &bytes)?;
    Ok(
        json!({"request_id":format!("code-rules-{digest}-{rev}"),"rules_digest":digest,"snapshot_id":rules["snapshot_id"],"review_revision":rev,"prompt":"Review the software rules before verification starts.","expires_at":expiry,
        "markdown_review":{"schema":"mn.markdown-review.v1","artifact_path":path,"sha256":file["sha256"],"item_count":items.len()}}),
    )
}
fn decision(record: &Value, req: &Value) -> Result<String, String> {
    for k in [
        "request_id",
        "rules_digest",
        "snapshot_id",
        "review_revision",
        "markdown_review",
    ] {
        if record["metadata"][k] != req[k] {
            return Err("Human decision identity differs from the exact revision".into());
        }
    }
    if req["expires_at"].as_u64().unwrap_or(0) <= now()
        || matches!(record["state"].as_str(), Some("expired" | "cancelled"))
    {
        return Err("Rule review expired or was cancelled".into());
    }
    let Some(answer) = record
        .pointer("/receipt/answer/option_id")
        .and_then(Value::as_str)
    else {
        return Ok("pending".into());
    };
    if !["approve", "reject", "revise"].contains(&answer) {
        return Err("Invalid human decision".into());
    }
    Ok(answer.into())
}
fn review(previous: &Value, conf: &Value) -> V {
    let original = read(&previous["rules"])?;
    let mut rules = original.clone();
    let expiry = match prior("rules-review-request.json")? {
        Some(v) => v["expires_at"].as_u64().ok_or("Invalid deadline")?,
        None => {
            let expires = now()
                + conf["review"]["human_review_timeout_seconds"]
                    .as_u64()
                    .unwrap_or(3600)
                    .clamp(1, 86400)
                    * 1000;
            commit(
                "rules-review-request.json",
                &json!({"snapshot_id":rules["snapshot_id"],"expires_at":expires}),
            )?;
            expires
        }
    };
    for rev in 1..=100 {
        let req = request(&rules, rev, expiry)?;
        let id = string(&req, "request_id")?;
        let mut rec = parse(&approvals::request(&req.to_string())?)?;
        loop {
            match decision(&rec, &req)?.as_str() {
                "approve" => {
                    let rules_ref = commit(
                        &format!(
                            "reviews/approved-{}.json",
                            req["rules_digest"].as_str().unwrap()
                        ),
                        &rules,
                    )?;
                    let receipt = json!({"status":"approved","snapshot_id":rules["snapshot_id"],"rules_digest":req["rules_digest"],"review_revision":rev,"request":req,"rules":rules_ref});
                    commit("rules-review.json", &receipt)?;
                    return Ok(json!({"capture":previous["capture"],"approval":receipt}));
                }
                "revise" => {
                    let edit = parse(
                        rec.pointer("/receipt/answer/text")
                            .and_then(Value::as_str)
                            .ok_or("Missing rule edit")?,
                    )?;
                    let title = string(&edit, "title")?;
                    let text = string(&edit, "markdown")?;
                    if edit.as_object().map(|m| m.len()) != Some(3)
                        || title.trim().is_empty()
                        || title.chars().count() > 120
                        || text.trim().is_empty()
                        || text.len() > 4000
                    {
                        return Err("Invalid rule edit".into());
                    }
                    let row = rules["rules"]
                        .as_array_mut()
                        .unwrap()
                        .iter_mut()
                        .find(|r| r["id"] == edit["id"])
                        .ok_or("Unknown edited rule")?;
                    let original_statement = list(&original, "rules")?
                        .iter()
                        .find(|r| r["id"] == edit["id"])
                        .ok_or("Missing original rule")?;
                    row["review_edit"] =
                        json!({"statement_changed":original_statement["statement"]!=text});
                    row["title"] = json!(title);
                    row["statement"] = json!(text);
                    row["origin"] = json!("supervisor");
                    for k in [
                        "subject",
                        "scope",
                        "conditions",
                        "modality",
                        "requirement_kind",
                    ] {
                        row.as_object_mut().unwrap().remove(k);
                    }
                    commit(&format!("reviews/revision-{rev}.json"), &rules)?;
                    break;
                }
                "reject" => return Err("The supervisor rejected this rules revision".into()),
                _ => {
                    progress("Waiting for the supervisor to review the exact rules revision");
                    std::thread::sleep(Duration::from_secs(2));
                    rec = parse(&approvals::status(id)?)?;
                }
            }
        }
    }
    Err("Rule edit limit exceeded".into())
}
fn approved(p: &Value) -> Result<(Value, Value), String> {
    let receipt = &p["approval"];
    let rules = read(&receipt["rules"])?;
    let c = read(&p["capture"])?;
    let req = &receipt["request"];
    let record = parse(&approvals::status(string(req, "request_id")?)?)?;
    if decision(&record, req) != (Ok("approve".into()))
        || hash(&rules.to_string()) != req["rules_digest"]
        || rules["snapshot_id"] != c["snapshot_id"]
        || identity(&c["sources"])? != c["snapshot_id"]
    {
        return Err("Exact approved rules and captured source are required".into());
    }
    Ok((rules, c))
}
fn verify(previous: &Value) -> V {
    let (rules, c) = approved(previous)?;
    let mut results = Vec::new();
    let sources = c["sources"].as_object().unwrap();
    let files = sources
        .iter()
        .map(|(path, t)| code_search::Source {
            path: path.to_string(),
            text: t.as_str().unwrap_or("").to_string(),
        })
        .collect::<Vec<_>>();
    for rule in list(&rules, "rules")? {
        let cache = format!(
            "verification/{}-{}.json",
            previous["approval"]["rules_digest"].as_str().unwrap(),
            string(rule, "id")?
        );
        if let Some(r) = prior(&cache)? {
            results.push(r);
            continue;
        }
        let mut evidence = BTreeMap::new();
        let mut history = vec![];
        let mut result = json!({"rule_id":rule["id"],"status":"unknown","evidence":[],"explanation":"No qualifying implementation evidence was established."});
        let turns = c["review_settings"]["max_turns_per_rule"]
            .as_u64()
            .unwrap_or(8)
            .clamp(3, 12);
        for turn in 0..turns {
            let packet = json!({"rule":rule,"snapshot_id":c["snapshot_id"],"project_map":sources.keys().take(256).collect::<Vec<_>>(),"history":history,"evidence":evidence});
            let response = ask("verify", &packet)?;
            let d = &response["decision"];
            let action = string(d, "action")?;
            if action == "finish" {
                let mut ids = BTreeSet::new();
                for id in list(d, "evidence_ids")? {
                    if let Some(id) = id.as_str() {
                        if evidence.contains_key(id) {
                            ids.insert(id.to_owned());
                        }
                    }
                }
                let status = string(d, "status")?;
                if status != "unknown"
                    && !ids.is_empty()
                    && d["evidence_ids"]
                        .as_array()
                        .is_some_and(|a| a.len() == ids.len())
                    && matches!(
                        (status, d["assessment"]["support"].as_str()),
                        ("pass", Some("supported")) | ("fail", Some("contradicted"))
                    )
                    && d["assessment"]["enforcement_evidence_ids"]
                        .as_array()
                        .is_some_and(|a| {
                            !a.is_empty()
                                && a.iter()
                                    .all(|id| id.as_str().is_some_and(|id| ids.contains(id)))
                        })
                    && d["assessment"]["scope_matches"] == true
                    && d["assessment"]["conditions_checked"] == true
                {
                    let judge = ask(
                        "judge",
                        &json!({"rule":rule,"proposal":d,"evidence":evidence}),
                    )?;
                    let critique = ask(
                        "critique",
                        &json!({"rule":rule,"proposal":d,"judge":judge["decision"],"evidence":evidence}),
                    )?;
                    if [&judge, &critique].iter().all(|answer| {
                        answer["decision"]["status"] == *status
                            && answer["decision"]["evidence_ids"]
                                .as_array()
                                .is_some_and(|a| {
                                    !a.is_empty()
                                        && a.iter().all(|id| {
                                            id.as_str().is_some_and(|id| ids.contains(id))
                                        })
                                })
                    }) {
                        result["status"] = json!(status);
                        result["evidence"] =
                            json!(ids.iter().map(|id| &evidence[id]).collect::<Vec<_>>());
                    }
                }
                result["explanation"] = d["explanation"].clone();
                break;
            }
            let observation = if action == "read" {
                let path = string(d, "path")?;
                let text = sources
                    .get(path)
                    .and_then(Value::as_str)
                    .ok_or("Model selected an uncaptured path")?;
                let first = d["start_line"].as_u64().unwrap_or(0) as usize;
                let end = d["end_line"].as_u64().unwrap_or(0) as usize;
                let lines = text.lines().collect::<Vec<_>>();
                if first == 0 || end < first || end > lines.len() || end - first >= 60 {
                    return Err("Model requested an invalid source range".into());
                }
                let id = format!("e{}", turn + 1);
                let item = json!({"id":id,"path":path,"start_line":first,"end_line":end,"text":lines[first-1..end].join("\n")});
                if ![".md", ".rst", ".adoc", ".txt"]
                    .iter()
                    .any(|s| path.ends_with(s))
                    && !path
                        .split('/')
                        .any(|s| s == "tests" || s.starts_with("test_"))
                {
                    evidence.insert(id, item.clone());
                }
                item
            } else {
                let query = d["query"]
                    .as_str()
                    .or_else(|| d["symbol"].as_str())
                    .ok_or("Missing search term")?;
                let hits = code_search::search(&files, query, 15)?;
                json!(hits
                    .iter()
                    .map(|h| json!({"path":h.path,"line":h.line,"text":h.text}))
                    .collect::<Vec<_>>())
            };
            history.push(json!({"request":d,"result":observation}));
        }
        commit(&cache, &result)?;
        results.push(result);
    }
    let verified = commit(
        "verification.json",
        &json!({"snapshot_id":c["snapshot_id"],"results":results,"rules":rules}),
    )?;
    Ok(
        json!({"capture":previous["capture"],"approval":previous["approval"],"verification":verified}),
    )
}
fn initialize(run: &str, previous: &Value) -> V {
    let (_, c) = approved(previous)?;
    let plan = plan(
        run,
        &selected_scope(&c["request"]["verification_scope"])?,
        &c,
        None,
    )?;
    let ledger = observations(
        c["request"]["assurance_evidence_sha256"].as_str(),
        &plan,
        &c["sources"],
    )?;
    let mut plan = plan;
    if let Some(pin) = c["request"]["assurance_basis_sha256"]
        .as_str()
        .filter(|s| !s.is_empty())
    {
        let mut basis = evidence(pin)?;
        if basis["schema"] != "otterdesk.assurance-basis.v1"
            || basis["subject"] != plan["subject"]
            || basis["baseline_subject"] != plan["baseline_subject"]
            || ledger["digest"].is_null()
            || basis["case_digest"] != ledger["digest"]
            || !matches!(basis["origin"].as_str(), Some("fixture" | "supplied"))
        {
            return Err("Assurance basis differs from the admitted case ledger".into());
        }
        for key in ["gates", "repair_checks"] {
            for id in basis[key].as_object().into_iter().flat_map(|m| m.values()) {
                if !list(&plan, "checks")?
                    .iter()
                    .any(|c| c["kind"] == "execution_record" && &c["id"] == id)
                {
                    return Err("Unbound assurance comparison".into());
                }
            }
        }
        for (id, items) in basis["locations"].as_object().into_iter().flatten() {
            if !list(&ledger, "cases")?
                .iter()
                .any(|row| row["id"] == id.as_str())
            {
                return Err("Unknown case location".into());
            }
            for loc in items.as_array().ok_or("Invalid case locations")? {
                let name = string(loc, "path")?;
                let line = loc["line"].as_u64().ok_or("Invalid location")?;
                if !list(&plan, "paths")?.iter().any(|s| s == name)
                    || line == 0
                    || line > c["sources"][name].as_str().map_or(0, |s| s.lines().count()) as u64
                {
                    return Err("Location outside captured scope".into());
                }
            }
        }
        basis["sha256"] = json!(pin);
        plan["assurance_basis"] = basis;
        plan = sign(plan);
    }
    let mut delegated = BTreeMap::new();
    let peers = c["request"]["collaboration_peers"].as_array();
    if c["request"]["collaboration_group_id"]
        .as_str()
        .is_some_and(|s| !s.is_empty())
    {
        for peer in peers.into_iter().flatten() {
            let role = string(peer, "blueprintId")?
                .strip_suffix("_verifier")
                .ok_or("Invalid verifier peer")?;
            category(role)?;
            if delegated.contains_key(role) {
                return Err("Duplicate dedicated specialist".into());
            }
            let checks = list(&plan, "checks")?
                .iter()
                .filter(|c| c["specialist"] == role)
                .cloned()
                .collect::<Vec<_>>();
            let selected = select(&ledger, role)?;
            let mut scoped = plan.clone();
            scoped["checks"] = json!(checks);
            scoped["observation_scope"] = json!(hash(&selected.to_string()));
            let scoped = sign(scoped);
            let mut files = BTreeMap::new();
            for check in list(&scoped, "checks")? {
                for key in [
                    "receipt_sha256",
                    "baseline_receipt_sha256",
                    "test_inventory_sha256",
                ] {
                    if let Some(pin) = check[key].as_str() {
                        match artifacts::read(&format!("runner-evidence/{pin}.json"), Some(pin)) {
                            Ok(body) => {
                                files.insert(pin, body);
                            }
                            Err(e) if e == "artifact_missing" => (),
                            Err(e) => return Err(e),
                        }
                    }
                }
            }
            let packet = json!({"schema":"software-verification.assignment.v1","role":role,"recipient_job_id":peer["jobId"],"plan":scoped,"sources":c["sources"],"baseline":c["baseline"],"observations":selected,"evidence_files":files});
            let reference = commit(&format!("specialists/assignments/{role}.json"), &packet)?;
            delegated.insert(role.to_owned(), reference);
        }
    }
    let plan_ref = commit("verification-plan.json", &plan)?;
    commit(
        "specialists/seed.json",
        &json!({"plan":plan_ref,"capture":previous["capture"],"approval":previous["approval"],"ledger":ledger,"delegated":delegated,
        "managed":c["request"]["collaboration_group_id"].as_str().is_some_and(|s|!s.is_empty())}),
    )
}
fn delegated_report(role: &str, packet: &Value, plan_id: &Value) -> V {
    let assignment = &packet["plan"];
    let job = string(packet, "recipient_job_id")?;
    let state_path = format!("specialists/dispatched/{role}.json");
    let sent = match prior(&state_path)? {
        Some(state) => state,
        None => {
            // The mailbox deduplicates this request if delivery preceded a lost receipt.
            let request_id = hash(&format!("{role}:{}", string(assignment, "plan_id")?));
            let message = mail_send(
                json!({"recipient_job_id":job,"kind":"assignment","request_id":request_id,
                    "subject":format!("{role} verification"),"text":"Review the assigned checks and return their evidence."}),
                packet,
            )?;
            let state = json!({"message":string(&message,"id")?,"expires_at":now()+180000});
            commit(&state_path, &state)?;
            state
        }
    };
    let message = string(&sent, "message")?;
    let expires = sent["expires_at"]
        .as_u64()
        .ok_or("Invalid reply deadline")?;
    loop {
        let replies = mail_list(
            json!({"kind":"result","reply_to":message,"include_acknowledged":true,"limit":1}),
        )?;
        if let Some(reply) = replies.first() {
            if reply["sender_job_id"] != job
                || reply["sender_blueprint_id"] != format!("{role}_verifier")
                || reply["reply_to"] != message
            {
                return Err("Mailbox reply has a mismatched sender or assignment".into());
            }
            let result = attachment(string(reply, "id")?, "attachment")?;
            if result["assignment_id"] != message || result["plan"] != *assignment {
                return Err("Mailbox reply has a mismatched assignment".into());
            }
            let mut records = list(&result, "records")?.clone();
            let verified = with_aspect(rollup(assignment, &records)?, &packet["observations"])?;
            if verified["aspect"] != result["aspect"]
                || list(&verified, "checks")?
                    .iter()
                    .any(|c| c["attempts"].as_array().is_none_or(Vec::is_empty))
            {
                return Err("Mailbox reply lacks independently verified evidence".into());
            }
            for record in &mut records {
                record["plan_id"] = plan_id.clone();
            }
            return Ok(json!({"records":records,"aspect":verified["aspect"],"plan_id":plan_id}));
        }
        if now() >= expires {
            return Ok(json!({"status":"pending","plan_id":plan_id}));
        }
        progress(&format!("Waiting for the {role} verifier's report"));
        std::thread::sleep(Duration::from_secs(2));
    }
}

fn inspect_role(seed: &Value, role: &str) -> V {
    let path = format!("specialists/reports/{role}.json");
    let (_, c) = approved(seed)?;
    let plan = read(&seed["plan"])?;
    let report = if let Some(saved) = prior(&path)? {
        saved
    } else if let Some(packet) = seed["delegated"].get(role) {
        delegated_report(role, &read(packet)?, &plan["plan_id"])?
    } else if seed["managed"] == true {
        return Err("Specialist is no longer assigned to this suite".into());
    } else {
        let records = attempts(&plan, &c["sources"], &c["baseline"], role)?;
        let r = with_aspect(rollup(&plan, &records)?, &select(&seed["ledger"], role)?)?;
        json!({"records":records,"aspect":r["aspect"],"plan_id":plan["plan_id"]})
    };
    commit(&path, &report)
}
fn round(work: &Value) -> V {
    let rf = &work["seed"];
    let seed = read(rf)?;
    let plan = read(&seed["plan"])?;
    let rev = work["_child"]["revision"]
        .as_u64()
        .ok_or("Missing child revision")?;
    let cache = format!("specialists/rounds/{rev}.json");
    if let Some(saved) = prior(&cache)? {
        return Ok(saved);
    }
    let mut tasks = vec![];
    let mut records = vec![];
    let mut aspects = BTreeMap::new();
    let mut missing = false;
    for role in ROLES {
        let delegated = seed["delegated"].get(role).is_some();
        if seed["managed"] == true && !delegated {
            aspects.insert(role, json!({"status":"removed"}));
            continue;
        }
        if missing {
            aspects.insert(role, json!({"status":"not_dispatched"}));
            continue;
        }
        match prior(&format!("specialists/reports/{role}.json"))? {
            Some(data) => {
                if data["plan_id"] != plan["plan_id"] {
                    return Err("Specialist report changed plan".into());
                }
                if data["status"] == "pending" {
                    missing = true;
                    aspects.insert(role, json!({"status":"pending"}));
                } else {
                    records.extend(list(&data, "records")?.clone());
                    aspects.insert(role,json!({"status":if delegated {"received"} else {"local"},"data":data["aspect"]}));
                }
            }
            None => {
                tasks.push(json!({"id":format!("{role}-report"),"template":format!("inspect_{role}"),"needs":[],"input":{"packet":rf,"role":role}}));
                break;
            }
        }
    }
    let result = if tasks.is_empty() {
        let mut report = rollup(&plan, &records)?;
        if missing && report["verdict"] == "PASS" {
            report["verdict"] = json!("INCONCLUSIVE")
        }
        if aspects
            .values()
            .filter_map(|a| a["data"]["cases"].as_array())
            .flatten()
            .any(|c| c["status"] == "unmet")
        {
            report["verdict"] = json!("FAIL")
        }
        report["aspects"] = json!(aspects);
        let r = commit("specialists/report.json", &report)?;
        json!({"decision":"stop","revision":rev,"reason":"Specialist evidence reconciled.","output":{"result":{"report":r,"capture":seed["capture"],"approval":seed["approval"]}}})
    } else {
        json!({"decision":"execute","revision":rev,"steps":tasks,"rationale":"Review the scoped source in the selected specialist workers.","evidence_refs":[seed["plan"]]})
    };
    commit(&cache, &result)?;
    Ok(result)
}
fn finish(p: &Value) -> V {
    let previous = &p["previous"];
    let (rules, c) = approved(previous)?;
    let verified = read(&previous["verification"])?;
    let special = read(&p["specialists"]["report"])?;
    if verified["snapshot_id"] != c["snapshot_id"]
        || special["plan"]["subject"] != c["snapshot_id"]
        || verified["rules"] != rules
    {
        return Err("Publication inputs refer to different source or rules".into());
    }
    let results = list(&verified, "results")?;
    let total = list(&rules, "rules")?.len();
    if results.len() != total {
        return Err("Missing rule result".into());
    }
    let failed = results.iter().filter(|r| r["status"] == "fail").count();
    let passed = results.iter().filter(|r| r["status"] == "pass").count();
    let (ci, mut reasons) = super::ci::report(&c["comparison"]["ci"], list(&rules, "rules")?)?;
    let approved: std::collections::BTreeSet<_> = list(&rules, "rules")?
        .iter()
        .map(|r| string(r, "id"))
        .collect::<Result<_, _>>()?;
    let mut mapped = std::collections::BTreeSet::new();
    for check in list(&special["plan"], "checks")? {
        for id in check["rule_ids"].as_array().into_iter().flatten() {
            let id = id.as_str().ok_or("Invalid mapped rule")?;
            if !approved.contains(id) {
                reasons.push(format!(
                    "A protected check refers to an unapproved rule: {id}"
                ));
            }
            mapped.insert(id);
        }
    }
    if matches!(
        special["plan"]["decision"].as_str(),
        Some("merge" | "release")
    ) && !approved.is_subset(&mapped)
    {
        reasons.push("Every approved rule requires an independent check for this decision.".into());
    }
    if total == 0 {
        reasons.push("The approved rule inventory is empty.".into());
    }
    let verdict = if failed > 0 || special["verdict"] == "FAIL" {
        "FAIL"
    } else if special["verdict"] == "BLOCKED" {
        "BLOCKED"
    } else if !reasons.is_empty()
        || passed != total
        || special["verdict"] != "PASS"
        || !list(&rules, "extraction_gaps")?.is_empty()
    {
        "INCONCLUSIVE"
    } else {
        "PASS"
    };
    let mut data = json!({"schema_version":"mn.software_rules.report.v1","rules":rules["rules"],"results":results,"summary":{"pass":passed,"fail":failed,"unknown":total-passed-failed},"snapshot_id":c["snapshot_id"],"rules_review":previous["approval"],"verdict":verdict,"specialists":special["aspects"],"specialist_report":special});
    data["reasons"] = json!(reasons);
    if !ci.is_null() {
        data["ci_evidence"] = ci;
    }
    let mut doc = document(&special, "Software verification report");
    doc["summary"] = json!(verdict);
    doc["sections"].as_array_mut().unwrap().insert(0,json!({"title":"Approved rules","blocks":list(&rules,"rules")?.iter().zip(results).map(|(r,v)|json!({"type":"paragraph","text":format!("{} · {}",r["statement"].as_str().unwrap_or(""),v["status"].as_str().unwrap_or("unknown"))})).collect::<Vec<_>>()}));
    publish(&data, &doc)
}
pub fn run(op: &str, run: &str, conf: &Value, p: &Value) -> V {
    match op {
        "coordinator-capture" => capture(conf, p),
        "extract-rules" => extract(&p["previous"], conf),
        "review-rules" => review(&p["previous"], conf),
        "verify-rules" => verify(&p["previous"]),
        "coordinate" => initialize(run, &p["previous"]),
        "plan-round" => Ok(json!({"child_plan":round(p)?})),
        "publish-suite" => finish(p),
        _ => {
            if let Some(role) = op.strip_prefix("inspect-") {
                category(role)?;
                if p["role"] != role {
                    return Err("Child role differs from template".into());
                }
                return inspect_role(&read(&p["packet"])?, role);
            }
            Err("Unknown verifier phase".into())
        }
    }
}
