//! Admit bounded user inputs before capture, model inference, or specialist dispatch.
use serde_json::{Value, json};
use std::collections::BTreeSet;

fn hex(s: &str, lengths: &[usize]) -> bool {
    lengths.contains(&s.len())
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn admit(input: &Value) -> Result<Value, String> {
    let request = input
        .as_object()
        .ok_or("Expected verification input fields")?;
    for k in ["assurance_evidence_sha256", "assurance_basis_sha256"] {
        match request.get(k) {
            None | Some(Value::Null) => {}
            Some(Value::String(s)) if s.is_empty() || hex(s, &[64]) => {}
            _ => return Err(format!("Expected a SHA-256 digest for {k}")),
        }
    }
    let raw = request.get("verification_scope").unwrap_or(&Value::Null);
    let scope = match raw {
        Value::Null => json!({}),
        Value::String(s) if s.is_empty() => json!({}),
        Value::String(s) if s.len() <= 64_000 => serde_json::from_str(
            &crate::mirror_neuron::skills::verification_checks::strict_json(s)?,
        )
        .map_err(|e| format!("Invalid verification scope: {e}"))?,
        Value::Object(_) if raw.to_string().len() <= 64_000 => raw.clone(),
        _ => return Err("Expected a verification scope of at most 64 KB".into()),
    };
    let map = scope
        .as_object()
        .ok_or("Verification scope must be a JSON object")?;
    if map.keys().any(|k| {
        !matches!(
            k.as_str(),
            "paths"
                | "checks"
                | "decision"
                | "repository"
                | "base_commit"
                | "integrated_commit"
                | "artifact_sha256"
                | "base_artifact_sha256"
                | "targets"
                | "subject_sha256"
                | "repair_of"
        )
    }) {
        return Err("Unknown verification scope field".into());
    }
    if map
        .get("decision")
        .is_some_and(|v| !matches!(v.as_str(), Some("merge" | "release" | "development")))
    {
        return Err("Invalid verification decision".into());
    }
    for k in [
        "base_commit",
        "integrated_commit",
        "artifact_sha256",
        "base_artifact_sha256",
        "subject_sha256",
        "repair_of",
    ] {
        let lengths: &[usize] = if k.ends_with("commit") {
            &[40, 64]
        } else {
            &[64]
        };
        if map
            .get(k)
            .is_some_and(|v| !v.as_str().is_some_and(|s| hex(s, lengths)))
        {
            return Err(format!("Invalid immutable identity {k}"));
        }
    }
    if let Some(v) = map.get("checks") {
        let checks = v
            .as_array()
            .filter(|c| c.len() <= 48)
            .ok_or("Expected at most 48 checks")?;
        let mut ids = BTreeSet::new();
        for c in checks {
            let id = c["id"].as_str().ok_or("Missing check ID")?;
            if id.starts_with("auto-") || !ids.insert(id) {
                return Err("Reserved or duplicate check ID".into());
            }
        }
    }
    Ok(input.clone())
}
