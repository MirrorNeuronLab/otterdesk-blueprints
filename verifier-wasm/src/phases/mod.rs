mod ci;
mod coordinator;
mod protected;
mod receipts;
mod specialist;
use crate::mirror_neuron::run::{artifacts, mailbox};
use crate::mirror_neuron::skills::{code_search, folder_files, web_report};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicU32, Ordering};

pub type V = Result<Value, String>;
pub fn string<'a>(v: &'a Value, k: &str) -> Result<&'a str, String> {
    v[k].as_str().ok_or_else(|| format!("Missing string {k}"))
}
fn list<'a>(v: &'a Value, k: &str) -> Result<&'a Vec<Value>, String> {
    v[k].as_array().ok_or_else(|| format!("Missing list {k}"))
}
fn parse(s: &str) -> V {
    serde_json::from_str(s).map_err(|e| e.to_string())
}
fn hash(s: &str) -> String {
    format!("{:x}", Sha256::digest(s.as_bytes()))
}
fn commit_text(path: &str, kind: &str, s: &str) -> V {
    parse(&artifacts::commit(path, kind, s)?)
}
fn commit(path: &str, v: &Value) -> V {
    commit_text(path, "json", &format!("{v}\n"))
}
fn read(r: &Value) -> V {
    parse(&artifacts::read(
        string(r, "path")?,
        Some(string(r, "sha256")?),
    )?)
}
fn prior(path: &str) -> Result<Option<Value>, String> {
    match artifacts::read(path, None) {
        Ok(s) => Ok(Some(parse(&s)?)),
        Err(e) if e == "artifact_missing" => Ok(None),
        Err(e) => Err(e),
    }
}
fn mail_list(filters: Value) -> Result<Vec<Value>, String> {
    Ok(list(&parse(&mailbox::list(&filters.to_string())?)?, "items")?.clone())
}
fn mail_send(mut envelope: Value, value: &Value) -> V {
    envelope["value"] = json!(value.to_string());
    parse(&mailbox::send(&envelope.to_string())?)
}
fn attachment(id: &str, field: &str) -> V {
    parse(&mailbox::attachment(id, field)?)
}
pub fn progress(message: &str) {
    static SEQ: AtomicU32 = AtomicU32::new(0);
    println!(
        "__MN_AGENT_BEACON__{}",
        json!({"progress_sequence":SEQ.fetch_add(1,Ordering::Relaxed)+1,"message":message})
    );
}
fn selected_scope(v: &Value) -> V {
    match v {
        Value::Null => Ok(json!({})),
        Value::String(s) if s.trim().is_empty() => Ok(json!({})),
        Value::String(s) => parse(s),
        Value::Object(_) => Ok(v.clone()),
        _ => Err("Invalid verification scope".into()),
    }
}
fn identity(s: &Value) -> Result<String, String> {
    let files = s
        .as_object()
        .ok_or("Expected captured files")?
        .iter()
        .map(|(p, t)| {
            Ok(code_search::Source {
                path: p.clone(),
                text: t.as_str().ok_or("Expected text")?.into(),
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    code_search::identity(&files)
}
fn captured(dir: &str, conf: &Value) -> V {
    let ext = list(conf, "extensions")?
        .iter()
        .map(|v| v.as_str().map(String::from).ok_or("Bad extension"))
        .collect::<Result<Vec<_>, _>>()?;
    let c = wit_bindgen::block_on(folder_files::capture(dir.into(), ext))?;
    let files: serde_json::Map<_, _> = c
        .files
        .into_iter()
        .map(|x| (x.path, json!(x.text)))
        .collect();
    Ok(json!({"sources":files,"omitted":c.omitted}))
}
fn subject(conf: &Value) -> V {
    let path = "/job/inputs/software_sources";
    let descriptor = std::path::Path::new(path).join("code-verifier-comparison.json");
    if !descriptor.exists() {
        let mut v = captured(path, conf)?;
        v["snapshot_id"] = json!(identity(&v["sources"])?);
        return Ok(v);
    }
    let bytes = std::fs::read_to_string(descriptor).map_err(|e| e.to_string())?;
    let meta = parse(&bytes)?;
    if bytes.len() > 512000 || meta["schema_version"] != "mn.code_verifier.comparison.v1" {
        return Err("Invalid comparison descriptor".into());
    }
    if let Some(receipt) = meta.get("ci").filter(|v| !v.is_null()) {
        ci::validate(receipt, string(&meta["head"], "commit")?)?;
    }
    let mut result = json!({"comparison":meta,"omitted":[]});
    for side in ["base", "head"] {
        let row = &meta[side];
        let dir = side;
        if !string(row, "commit")?
            .bytes()
            .all(|c| c.is_ascii_hexdigit())
            || ![40, 64].contains(&string(row, "commit")?.len())
        {
            return Err("Invalid pinned comparison side".into());
        }
        let capture = captured(&format!("{path}/{dir}"), conf)?;
        if !list(&capture, "omitted")?.is_empty() {
            return Err("Incomplete prepared comparison".into());
        }
        let files = capture["sources"]
            .as_object()
            .ok_or("Missing comparison snapshot")?;
        let pairs = files
            .iter()
            .map(|(p, t)| Ok(json!([p, hash(t.as_str().ok_or("Expected source text")?)])))
            .collect::<Result<Vec<_>, String>>()?;
        if hash(&json!(pairs).to_string()) != row["sha256"]
            || row["omitted"].as_u64().is_none_or(|n| n > 30000)
        {
            return Err("Prepared snapshot differs from its pin".into());
        }
        let id = identity(&capture["sources"])?;
        result["comparison"][side]["snapshot_id"] = json!(id);
        if side == "head" {
            result["snapshot_id"] = json!(id);
            result["sources"] = capture["sources"].clone()
        } else {
            result["baseline"] = capture["sources"].clone()
        }
    }
    Ok(result)
}
fn publish(data: &Value, doc: &Value) -> V {
    let rendered = web_report::render(&doc.to_string())?;
    let report = commit_text("report.md", "markdown", &rendered.markdown)?;
    let web = commit_text("web/index.html", "html", &rendered.html)?;
    let handle = parse(&artifacts::static_report(
        "web/index.html",
        string(&web, "sha256")?,
        string(doc, "title")?,
    )?)?;
    let ui = commit("web_ui.json", &handle)?;
    let final_ref = commit("final_artifact.json", data)?;
    let result = json!({"status":"completed","final_artifact":final_ref,"report":report,"web_report":web,"web_ui":ui});
    let receipt = commit("result.json", &result)?;
    let mut files = serde_json::Map::new();
    for reference in [&report, &web, &ui, &final_ref, &receipt] {
        files.insert(string(reference, "path")?.to_owned(), reference.clone());
    }
    if let Some(rows) = prior("publication-inputs.json")? {
        for reference in rows
            .as_array()
            .ok_or("Invalid captured publication inventory")?
        {
            files.insert(string(reference, "path")?.into(), reference.clone());
        }
        for (name, kind) in [
            ("rules.json", "json"),
            ("rules.md", "markdown"),
            ("static-analysis.json", "json"),
            ("verification-plan.json", "json"),
            ("verification.json", "json"),
            ("capture.json", "json"),
            ("rules-review-request.json", "json"),
            ("rules-review.json", "json"),
            ("extraction-status.json", "json"),
        ] {
            let body = artifacts::read(name, None)?;
            files.insert(name.into(), commit_text(name, kind, &body)?);
        }
    }
    artifacts::publish(&Value::Object(files).to_string())?;
    Ok(receipt)
}
pub fn run(op: &str, run: &str, conf: &Value, p: &Value) -> V {
    match op {
        "specialist-capture" => specialist::capture(run, conf, p),
        "specialist-evaluate" => specialist::evaluate(run, conf, &p["previous"]),
        "specialist-publish" => specialist::publish_report(&p["report"]),
        _ => coordinator::run(op, run, conf, p),
    }
}
