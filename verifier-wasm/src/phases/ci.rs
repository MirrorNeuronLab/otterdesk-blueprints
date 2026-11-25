//! Bind imported CI statuses to the proposed revision and the approved rules.
use super::*;
use std::collections::BTreeSet;

fn label(v: &Value, n: usize) -> bool {
    v.as_str().is_some_and(|s| {
        !s.trim().is_empty() && s.chars().count() <= n && !s.chars().any(char::is_control)
    })
}
pub fn validate(receipt: &Value, head: &str) -> Result<(), String> {
    let sha = string(receipt, "sha256")?;
    if receipt.as_object().is_none_or(|m| m.len() != 4)
        || receipt["commit"] != head
        || !label(&receipt["file"], 240)
        || sha.len() != 64
        || !sha
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err("CI receipt differs from its protected revision or file identity".into());
    }
    let checks = list(receipt, "checks")?;
    if !(1..=500).contains(&checks.len()) {
        return Err("Invalid CI check inventory".into());
    }
    let mut seen = BTreeSet::new();
    for row in checks {
        let rule = string(row, "rule_id")?;
        if row.as_object().is_none_or(|m| m.len() != 3)
            || !rule
                .as_bytes()
                .first()
                .is_some_and(|b| b.is_ascii_alphabetic())
            || rule.len() > 64
            || !rule
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
            || !label(&row["test"], 360)
            || !matches!(
                row["status"].as_str(),
                Some("passed" | "failed" | "skipped" | "missing" | "mixed")
            )
            || !seen.insert((rule, string(row, "test")?))
        {
            return Err("Invalid or duplicated CI mapping".into());
        }
    }
    Ok(())
}
pub fn report(receipt: &Value, rules: &[Value]) -> Result<(Value, Vec<String>), String> {
    if receipt.is_null() {
        return Ok((Value::Null, vec![]));
    }
    let mut view = receipt.clone();
    let mut conflicts = BTreeSet::new();
    for row in view["checks"].as_array_mut().ok_or("Missing CI mappings")? {
        let mapping = match rules.iter().find(|r| r["id"] == row["rule_id"]) {
            None => "rule_missing",
            Some(rule) if rule["review_edit"]["statement_changed"] == true => "rule_edited",
            Some(_) => "linked",
        };
        row["mapping"] = json!(mapping);
        if mapping == "linked" && matches!(row["status"].as_str(), Some("failed" | "mixed")) {
            conflicts.insert(format!(
                "Imported CI reported a failed or mixed result for approved rule {}.",
                string(row, "rule_id")?
            ));
        }
    }
    Ok((view, conflicts.into_iter().collect()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ci_checks_bind_to_the_revision_and_unedited_approved_rules() {
        let head = "a".repeat(40);
        let receipt = json!({"commit":head,"file":"ci.xml","sha256":"b".repeat(64),"checks":[{"rule_id":"names","test":"name_required","status":"failed"}]});
        assert!(validate(&receipt, &head).is_ok());
        assert!(validate(&receipt, &"c".repeat(40)).is_err());
        let (_, reasons) = report(&receipt, &[json!({"id":"names"})]).unwrap();
        assert_eq!(reasons.len(), 1);
        let (view, reasons) = report(
            &receipt,
            &[json!({"id":"names","review_edit":{"statement_changed":true}})],
        )
        .unwrap();
        assert!(reasons.is_empty());
        assert_eq!(view["checks"][0]["mapping"], "rule_edited");
    }
}
