//! Qualify only the externally pinned, offline receipt for the frozen revision.
use super::*;
use std::collections::BTreeSet;

fn check_side(check: &Value, plan: &Value, sources: &Value) -> V {
    let pin = string(check, "receipt_sha256")?;
    let receipt = specialist::evidence(pin)?;
    if receipt["schema_version"] != "mn.verification.execution.v1"
        || receipt["check_id"] != check["id"]
        || receipt["target"] != check["target"]
        || receipt["suite_sha256"] != check["suite_sha256"]
        || [
            "subject",
            "base_commit",
            "revision",
            "artifact_sha256",
            "repository",
        ]
        .iter()
        .any(|k| receipt[*k] != plan[*k])
    {
        return Err(
            "Execution receipt differs from the approved check, subject or revision.".into(),
        );
    }
    if plan["decision"] == "release"
        && (plan["verified_artifact"].is_null()
            || plan["verified_artifact"] != receipt["artifact_sha256"])
    {
        return Err("The release artifact has not been verified.".into());
    }
    for key in ["runner_sha256", "fixture_sha256", "suite_sha256"] {
        let pin = string(&receipt, key)?;
        if pin.len() != 64
            || !pin
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        {
            return Err(format!("Invalid {key}"));
        }
    }
    let states = receipt["cases"]
        .as_object()
        .ok_or("Missing recorded cases")?;
    let expected = list(check, "cases")?
        .iter()
        .map(|v| v.as_str().ok_or("Invalid approved case"))
        .collect::<Result<BTreeSet<_>, _>>()?;
    if expected.is_empty()
        || expected.len() != states.len()
        || states.keys().any(|name| !expected.contains(name.as_str()))
    {
        return Err("Discovered cases differ from protected inventory.".into());
    }
    let mut outcomes = BTreeSet::new();
    let mut count = 0;
    for (name, history) in states {
        let rows = history
            .as_array()
            .filter(|a| (1..=8).contains(&a.len()))
            .ok_or("Invalid case history")?;
        let mut attempts = BTreeSet::new();
        for value in rows {
            let state = value.as_str().ok_or("Invalid case status")?;
            if !["passed", "failed", "skipped", "blocked", "inconclusive"].contains(&state) {
                return Err("Invalid case status".into());
            }
            attempts.insert(state);
            count += usize::from(matches!(state, "passed" | "failed"));
        }
        outcomes.insert(if attempts.len() == 1 {
            *attempts.first().unwrap()
        } else {
            "inconclusive"
        });
        for (metric, expected) in check["expected_counts"].as_object().into_iter().flatten() {
            let samples = receipt["observations"]["case_counts"][name][metric]
                .as_array()
                .filter(|s| s.len() == rows.len())
                .ok_or("Missing per-attempt count")?;
            if expected.as_u64().is_none() || samples.iter().any(|v| v.as_u64().is_none()) {
                return Err("Invalid event count".into());
            }
            if samples.iter().any(|v| v != expected) {
                outcomes.insert("failed");
            }
        }
    }
    let observed = &receipt["observations"];
    if let Some(counts) = observed["test_counts"].as_object() {
        let mut total = 0;
        for key in ["passed", "failed", "skipped", "inconclusive"] {
            let n = counts
                .get(key)
                .and_then(Value::as_u64)
                .filter(|n| *n <= 10_000_000)
                .ok_or("Invalid runner counts")?;
            total += n;
            if key != "passed" && n > 0 && outcomes.contains("passed") {
                outcomes.insert("inconclusive");
            }
        }
        if total == 0 {
            return Err("Runner reported an empty inventory".into());
        }
    }
    for (key, metric) in [
        ("min_coverage_percent", "coverage_percent"),
        ("max_elapsed_ms", "elapsed_ms"),
        ("max_peak_memory_mb", "peak_memory_mb"),
    ] {
        if let Some(limit) = check.get(key) {
            let limit = limit
                .as_f64()
                .filter(|v| *v > 0.0)
                .ok_or("Invalid approved threshold")?;
            let val = if metric == "peak_memory_mb" {
                let samples = observed[metric]
                    .as_array()
                    .filter(|v| (3..=100).contains(&v.len()))
                    .ok_or("Missing memory profile")?;
                samples
                    .iter()
                    .map(|v| {
                        v.as_f64()
                            .filter(|s| *s >= 0.0)
                            .ok_or("Invalid memory profile")
                    })
                    .collect::<Result<Vec<_>, _>>()?
                    .into_iter()
                    .reduce(f64::max)
            } else {
                observed[metric].as_f64()
            };
            let n = val
                .filter(|n| *n >= 0.0)
                .ok_or("Missing runner measurement")?;
            if (metric == "coverage_percent" && (n < limit || n > 100.0))
                || (metric != "coverage_percent" && n > limit)
            {
                outcomes.insert("failed");
            }
        }
    }
    let replay = receipt.get("replay");
    if let Some(r) = replay {
        if r.as_object().is_none_or(|v| v.len() != 4)
            || ["seed", "environment", "simulation", "reset"]
                .iter()
                .any(|k| {
                    r[*k]
                        .as_str()
                        .is_none_or(|s| s.trim().is_empty() || s.len() > 300)
                })
        {
            return Err("Invalid workload replay identity".into());
        }
    }
    let runs = receipt["runs"].as_array();
    if receipt.get("runs").is_some() && runs.is_none() {
        return Err("Invalid run details".into());
    }
    if let Some(runs) = runs.filter(|v| !v.is_empty()) {
        if states.len() != 1 || runs.len() > 8 {
            return Err("Case history differs from reported attempts".into());
        }
        let history = states.values().next().unwrap().as_array().unwrap();
        if history.len() != runs.len()
            || runs.iter().zip(history).any(|(r, state)| {
                r["status"] != *state
                    || r.get("assertion_line").is_some_and(|n| {
                        state != "failed"
                            || n.as_u64().is_none_or(|i| !(1..=9_999_999).contains(&i))
                    })
            })
        {
            return Err("Run details differ from protected case history".into());
        }
    }
    let status = ["failed", "blocked", "inconclusive", "skipped", "passed"]
        .into_iter()
        .find(|s| outcomes.contains(s))
        .ok_or("Empty evidence")?;
    let reference = json!({"path":format!("{pin}.json"),"sha256":pin});
    let detail = format!(
        "Checked {} protected cases on {}.",
        states.len(),
        string(check, "target")?
    );
    let findings = if status == "passed" {
        vec![]
    } else {
        vec![
            json!({"expected":check["requirement"],"observed":detail,"evidence":reference,"reproduce":"Inspect the named case history in the pinned runner receipt.","recommendation":"Recheck the recorded suite and fixtures."}),
        ]
    };
    let mut row = json!({"status":status,"executed":count,"observed":detail,"findings":findings,"evidence":[reference],"target":check["target"],
        "cases":states,"observations":observed,"runner_sha256":receipt["runner_sha256"],"fixture_sha256":receipt["fixture_sha256"],
        "test_id":receipt["test_id"],"runs":runs,"replay":replay});
    if check.get("behavior").is_some() {
        super::protected::behavior(&mut row, check, plan, sources)?;
    }
    if check.get("test_inventory_sha256").is_some() {
        super::protected::inventory(&mut row, check, plan, sources)?;
    }
    Ok(row)
}

fn profile(row: &Value) -> Option<(usize, f64)> {
    let values = row["observations"]["samples_ms"].as_array()?;
    if !(3..=100).contains(&values.len()) {
        return None;
    }
    let mut ms = values
        .iter()
        .map(|v| v.as_f64().filter(|n| (0.0..=86_400_000.0).contains(n)))
        .collect::<Option<Vec<_>>>()?;
    ms.sort_by(f64::total_cmp);
    Some((ms.len(), ms[(95 * ms.len()).div_ceil(100) - 1]))
}

pub fn check(check: &Value, plan: &Value, sources: &Value, baseline: &Value) -> V {
    let mut result = check_side(check, plan, sources)?;
    if !baseline.is_object() {
        if check.get("max_p95_increase_percent").is_some() && result["status"] == "passed" {
            result["status"] = json!("inconclusive");
            result["observed"] =
                json!("A paired baseline is required for the protected performance budget.");
        }
        return Ok(result);
    }
    let mut before = plan.clone();
    before["revision"] = plan["base_commit"].clone();
    before["subject"] = plan["baseline_subject"].clone();
    before["artifact_sha256"] = plan["base_artifact_sha256"].clone();
    before["verified_artifact"] = plan["verified_base_artifact"].clone();
    if plan["scope_paths"].as_array().is_none_or(|v| v.is_empty()) {
        before["paths"] = json!(baseline.as_object().unwrap().keys().collect::<Vec<_>>());
    }
    let mut prior_check = check.clone();
    prior_check["receipt_sha256"] = check["baseline_receipt_sha256"].clone();
    prior_check
        .as_object_mut()
        .unwrap()
        .remove("test_inventory_sha256");
    let prior = check_side(&prior_check, &before, baseline)
        .unwrap_or_else(|e| json!({"status":"inconclusive","observed":e}));
    let same = ["target", "runner_sha256", "fixture_sha256"]
        .iter()
        .all(|k| !prior[*k].is_null() && prior[*k] == result[*k])
        && prior["replay"] == result["replay"];
    let mixed = [&prior, &result].into_iter().any(|side| {
        side["cases"]
            .as_object()
            .into_iter()
            .flatten()
            .any(|(_, v)| {
                v.as_array().is_some_and(|history| {
                    history.iter().any(|s| s == "failed") && history.iter().any(|s| s == "passed")
                })
            })
    });
    let mut label = if mixed {
        "Intermittent failure"
    } else if !same {
        "Not comparable"
    } else {
        match (prior["status"].as_str(), result["status"].as_str()) {
            (Some("passed"), Some("passed")) => "Passed on both revisions",
            (Some("passed"), Some("failed")) => "New regression",
            (Some("failed"), Some("failed")) => "Existing defect",
            (Some("failed"), Some("passed")) if check["behavior"]["intentional_change"] == true => {
                "Intentional behavior change"
            }
            (Some("failed"), Some("passed")) => "Resolved defect",
            _ => "Not comparable",
        }
    };
    if let Some(limit) = check.get("max_p95_increase_percent") {
        let limit = limit
            .as_f64()
            .filter(|n| *n >= 0.0)
            .ok_or("Invalid performance budget")?;
        match (label, profile(&prior), profile(&result)) {
            ("Passed on both revisions", Some((n, old)), Some((m, new)))
                if n == m && old > 0.0 && prior["replay"].is_object() =>
            {
                let increase = (new / old - 1.0) * 100.0;
                result["performance"] = json!({"baseline_p95_ms":old,"candidate_p95_ms":new,"increase_percent":increase,"limit_percent":limit});
                if increase > limit {
                    label = "New regression";
                    result["status"] = json!("failed");
                    result["observed"] = json!("The paired workload exceeded its latency budget.");
                    let evidence = result["evidence"][0].clone();
                    result["findings"].as_array_mut().unwrap().push(json!({"expected":format!("p95 grows by at most {limit}%."),"observed":format!("p95 moved from {old} to {new} ms."),"evidence":evidence,"recommendation":"Compare the profiles of the pinned workload.","reproduce":"Repeat both revisions with the same protected runner and fixtures."}));
                }
            }
            _ if result["status"] == "passed" => {
                result["status"] = json!("inconclusive");
                result["observed"] =
                    json!("The two profiles did not establish a comparable replay.");
            }
            _ => (),
        }
    }
    result["comparison"] =
        json!({"classification":label,"baseline":prior,"candidate_status":result["status"]});
    Ok(result)
}
