//! Bind independently recorded observations to the exact approved source.
use super::*;
use crate::mirror_neuron::skills::static_code_analysis::{self as analysis, Declaration};
use std::collections::{BTreeMap, BTreeSet};

fn text<'a>(sources: &'a Value, plan: &Value, path: &str) -> Result<&'a str, String> {
    if !list(plan, "paths")?.iter().any(|v| v == path) {
        return Err("Reference outside the frozen source selection".into());
    }
    sources[path]
        .as_str()
        .ok_or_else(|| "Referenced source was not captured".into())
}

fn passage(source: &str, first: u64, last: u64) -> Result<String, String> {
    if first == 0 || last < first {
        return Err("Invalid source range".into());
    }
    let lines = source.split_inclusive('\n').collect::<Vec<_>>();
    let selected = lines
        .get((first - 1) as usize..last as usize)
        .ok_or("Range outside captured source")?;
    Ok(selected.concat())
}

fn pinned_line(
    link: &Value,
    sources: &Value,
    plan: &Value,
    extensions: &[&str],
) -> Result<(), String> {
    let path = string(link, "path")?;
    if !extensions
        .iter()
        .any(|ext| path.to_ascii_lowercase().ends_with(ext))
    {
        return Err("Invalid reference type".into());
    }
    let n = link["line"].as_u64().ok_or("Invalid reference line")?;
    if hash(&passage(text(sources, plan, path)?, n, n)?) != string(link, "sha256")? {
        return Err("Evidence source line changed".into());
    }
    Ok(())
}

fn test_file(path: &str) -> bool {
    let name = path.rsplit('/').next().unwrap_or(path);
    name.ends_with(".py") && (name.starts_with("test_") || name.ends_with("_test.py"))
}

fn declaration<'a>(defs: &'a [Declaration], symbol: &str) -> Result<&'a Declaration, String> {
    let mut found = defs.iter().filter(|d| d.symbol == symbol);
    let value = found.next().ok_or("Missing declared symbol")?;
    if found.next().is_some() {
        return Err("Ambiguous declared symbol".into());
    }
    Ok(value)
}

fn anchor(sources: &Value, plan: &Value, spec: &Value) -> Result<(Value, String), String> {
    let path = string(spec, "path")?;
    let src = text(sources, plan, path)?;
    let symbol = string(spec, "symbol")?;
    let defs = analysis::python_declarations(src)?;
    let d = declaration(&defs, symbol)?;
    let digest = hash(&passage(src, d.first_line.into(), d.last_line.into())?);
    Ok((
        json!({"path":path,"line":d.line,"end_line":d.last_line,"symbol":symbol,"sha256":hash(src)}),
        digest,
    ))
}

pub fn behavior(
    record: &mut Value,
    check: &Value,
    plan: &Value,
    sources: &Value,
) -> Result<(), String> {
    let b = &check["behavior"];
    let spec = &b["specification"];
    let (path, first, last) = (
        string(spec, "path")?,
        spec["start_line"].as_u64().ok_or("Missing start line")?,
        spec["end_line"].as_u64().ok_or("Missing end line")?,
    );
    if last.saturating_sub(first) >= 40
        || hash(&passage(text(sources, plan, path)?, first, last)?) != string(spec, "sha256")?
    {
        return Err("Protected specification passage changed".into());
    }
    let test = &b["test"];
    let (oracle, digest) = anchor(sources, plan, test)?;
    let test_path = string(test, "path")?;
    let selector = format!(
        "{test_path}::{}",
        string(test, "symbol")?.replace('.', "::")
    );
    if !test_file(test_path) || b["test_sha256"] != digest || record["test_id"] != selector {
        return Err("Protected test differs from the recorded selector or body".into());
    }
    let impls = list(b, "implementation")?;
    if !(1..=8).contains(&impls.len()) {
        return Err("Expected one to eight implementation anchors".into());
    }
    let locations = impls
        .iter()
        .map(|s| anchor(sources, plan, s).map(|(reference, _)| reference))
        .collect::<Result<Vec<_>, _>>()?;
    let mut review = json!({"expectation":check["requirement"],"rule_ids":check["rule_ids"],"setup":b["setup"],"impact":b["impact"],"uncertainty":b["limits"],"selector":selector,"locations":locations,"test_location":oracle,"specification":spec});
    let runs = record["runs"].as_array().cloned().unwrap_or_default();
    let failed: Vec<_> = runs.iter().filter(|v| v["status"] == "failed").collect();
    let assertion = failed.first().and_then(|r| r["assertion_line"].as_u64());
    if let Some(line) = assertion {
        if failed
            .iter()
            .all(|r| r["assertion_line"].as_u64() == Some(line))
            && line >= oracle["line"].as_u64().unwrap()
            && line <= oracle["end_line"].as_u64().unwrap()
            && analysis::assertion_at(text(sources, plan, test_path)?, line as u32)?
        {
            review["assertion"] =
                json!({"path":test_path,"line":line,"sha256":hash(text(sources,plan,test_path)?)});
        }
    }
    if let Some(quality) = b.get("test_quality") {
        let controls = list(quality, "controls")?;
        let counts = record["observations"]["case_counts"]
            .as_object()
            .ok_or("Missing fixture observations")?;
        for control in controls {
            let k = control.as_str().ok_or("Invalid fixture control")?;
            let expected = check["expected_counts"][k]
                .as_u64()
                .ok_or("Unbound fixture control")?;
            if counts.values().any(|case| {
                case[k]
                    .as_array()
                    .is_none_or(|a| a.is_empty() || a.iter().any(|n| n.as_u64() != Some(expected)))
            }) {
                return Err("Independent fixture controls did not pass".into());
            }
        }
        if record["cases"]
            .as_object()
            .into_iter()
            .flatten()
            .any(|(_, seq)| {
                seq.as_array()
                    .is_some_and(|a| a.iter().any(|s| s == "failed"))
            })
            && (review["assertion"].is_null() || runs.is_empty() || failed.len() != runs.len())
        {
            return Err("The trial did not reproduce a single protected assertion".into());
        }
    }
    record["evidence"]
        .as_array_mut()
        .ok_or("Missing evidence")?
        .extend(
            std::iter::once(spec.clone())
                .chain(std::iter::once(oracle))
                .chain(locations),
        );
    record["behavior"] = review;
    Ok(())
}

pub fn inventory(
    record: &mut Value,
    check: &Value,
    plan: &Value,
    sources: &Value,
) -> Result<(), String> {
    let pin = string(check, "test_inventory_sha256")?;
    let inv = specialist::evidence(pin)?;
    let origin = string(&inv, "origin")?;
    if origin.trim().is_empty()
        || origin.len() > 600
        || inv["subject"] != plan["subject"]
        || inv["revision"] != plan["revision"]
        || inv["suite_sha256"] != check["suite_sha256"]
        || inv["check_id"] != check["id"]
    {
        return Err("Inventory identifies a different source, case or suite".into());
    }
    let rows = list(&inv, "cases")?;
    if !(1..=5000).contains(&rows.len()) {
        return Err("Invalid inventory size".into());
    }
    let mut defs = BTreeMap::new();
    let mut seen = BTreeSet::new();
    let mut counts = BTreeMap::new();
    let (mut generated, mut reviewed) = (0, 0);
    for row in rows {
        let (id, path, status) = (
            string(row, "id")?,
            string(row, "path")?,
            string(row, "status")?,
        );
        if !seen.insert(id)
            || !test_file(path)
            || !["passed", "failed", "skipped", "inconclusive"].contains(&status)
        {
            return Err("Invalid or duplicate inventory case".into());
        }
        let selector = id
            .strip_prefix(&format!("{path}::"))
            .ok_or("Different inventory test module")?
            .split('[')
            .next()
            .unwrap()
            .replace("::", ".");
        if !selector.rsplit('.').next().unwrap().starts_with("test_") {
            return Err("Invalid test declaration".into());
        }
        if !defs.contains_key(path) {
            defs.insert(
                path,
                analysis::python_declarations(text(sources, plan, path)?)?,
            );
        }
        let d = declaration(&defs[path], &selector)?;
        if row["line"].as_u64() != Some(d.line.into()) {
            return Err("Inventory declaration line differs from the capture".into());
        }
        *counts.entry(status).or_insert(0u64) += 1;
        if let Some(link) = row.get("origin") {
            pinned_line(link, sources, plan, &[".md", ".rst", ".txt"])?;
            match string(link, "basis")? {
                "generator_record" => {
                    generated += 1;
                    if let Some(p) = link.get("producer") {
                        pinned_line(
                            p,
                            sources,
                            plan,
                            &[".py", ".js", ".ts", ".rb", ".go", ".json", ".yml", ".yaml"],
                        )?;
                    }
                }
                "reviewed_link" if link.get("producer").is_none() => reviewed += 1,
                _ => return Err("Invalid test origin".into()),
            }
        }
    }
    for state in ["passed", "failed", "skipped", "inconclusive"] {
        if record["observations"]["test_counts"][state].as_u64()
            != Some(*counts.get(state).unwrap_or(&0))
        {
            return Err("Test inventory and pinned runner totals differ".into());
        }
    }
    record["test_inventory"] = json!({"origin":origin,"cases":rows,"linked":generated+reviewed,"generator_links":generated,"reviewed_links":reviewed,"total":rows.len(),"sha256":pin});
    Ok(())
}
