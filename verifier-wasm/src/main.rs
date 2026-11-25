mod admission;
wit_bindgen::generate!({path: "wit", world: "verifier", generate_all});

use mirror_neuron::skills::{
    code_search, comparison_evidence, folder_files, static_code_analysis, verification_checks,
    web_report,
};
use serde_json::{Value, json};
use std::{fs, process::ExitCode};

fn main() -> ExitCode {
    match run() {
        Ok(value) => {
            if let Err(error) = fs::write("/job/output.json", value.to_string()) {
                eprintln!("{error}");
                return ExitCode::FAILURE;
            }
            println!("{value}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<Value, String> {
    let config: Value =
        serde_json::from_slice(&fs::read("/job/config.json").map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    let input: Value = serde_json::from_slice(
        &fs::read("/job/mirror_neuron_input.json").map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let operation = config["operation"]
        .as_str()
        .ok_or("Missing verification operation")?;
    let input = input
        .get("step_input")
        .or_else(|| input.pointer("/body/step_input"))
        .unwrap_or(&input);
    if std::path::Path::new("/job/mirror_neuron_context.json").exists() {
        println!(
            "__MN_AGENT_BEACON__{}",
            json!({"progress_sequence":1,"message":"Processing verification input"})
        );
    }
    let value = match operation {
        "assess" => serde_json::from_str(&comparison_evidence::assess(
            &input["selected"].to_string(),
        )?)
        .map_err(|e| e.to_string())?,
        "admit" => admission::admit(input)?,

        "capture" => {
            let extensions: Vec<String> = serde_json::from_value(
                input
                    .get("extensions")
                    .unwrap_or(&config["extensions"])
                    .clone(),
            )
            .map_err(|e| e.to_string())?;
            let captured = wit_bindgen::block_on(folder_files::capture("/job/inputs".into(), extensions))?;
            let corpus: Vec<_> = captured
                .files
                .into_iter()
                .map(|s| code_search::Source {
                    path: s.path,
                    text: s.text,
                })
                .collect();
            let id = code_search::identity(&corpus)?;
            json!({"subject":id, "omitted":captured.omitted, "files":corpus.iter().map(|s|(&s.path,&s.text)).collect::<std::collections::BTreeMap<_,_>>()})
        }
        "snapshot" => {
            let sources = input["sources"]
                .as_object()
                .ok_or("Expected a captured source map")?;
            let files = sources
                .iter()
                .map(|(path, text)| {
                    Ok(code_search::Source {
                        path: path.clone(),
                        text: text.as_str().ok_or("Source must be UTF-8 text")?.into(),
                    })
                })
                .collect::<Result<Vec<_>, String>>()?;
            json!({"subject": code_search::identity(&files)?})
        }
        "reconcile" => serde_json::from_str(&verification_checks::reconcile(
            &input["signed_plan"].to_string(),
            &input["records"].to_string(),
        )?)
        .map_err(|e| e.to_string())?,
        "syntax" => {
            let issues = static_code_analysis::python_syntax(field(&input, "source")?)?;
            json!({"diagnostics":issues.into_iter().map(|d|json!({"line":d.line,"message":d.message})).collect::<Vec<_>>()})
        }
        "json-contract" => {
            json!({"passed":verification_checks::json_contract(field(&input,"source")?, &input["keys"].to_string())?})
        }
        "schema-cases" => serde_json::from_str(&verification_checks::schema_cases(
            field(&input, "source")?,
            &input["cases"].to_string(),
        )?)
        .map_err(|e| e.to_string())?,
        "compare" => serde_json::from_str(&comparison_evidence::compare(
            &input["expected"].to_string(),
            input.get("baseline").map(Value::to_string).as_deref(),
            input.get("candidate").map(Value::to_string).as_deref(),
        )?)
        .map_err(|e| e.to_string())?,
        "report" => {
            let rendered = web_report::render(&input["document"].to_string())?;
            json!({"markdown":rendered.markdown,"html":rendered.html})
        }
        _ => return Err(format!("Unknown verification operation {operation}")),
    };
    Ok(json!({"outputs":{"result":value},"status":"completed","artifacts":[],"metrics":{}}))
}
fn field<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("Missing string field {key}"))
}
