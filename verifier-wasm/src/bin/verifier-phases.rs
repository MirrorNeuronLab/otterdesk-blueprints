wit_bindgen::generate!({path:"wit", world:"phases", generate_all});
#[path = "../phases/mod.rs"]
mod phases;
use serde_json::{Value, json};
use std::{fs, process::ExitCode};

fn run() -> Result<(), String> {
    let read = |name: &str| -> Result<Value, String> {
        serde_json::from_slice(&fs::read(format!("/job/{name}")).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())
    };
    let conf = read("config.json")?;
    let input = read("mirror_neuron_input.json")?;
    let ctx = read("mirror_neuron_context.json")?;
    let payload = input
        .get("step_input")
        .or_else(|| input.pointer("/body/step_input"))
        .unwrap_or(&input);
    let op = phases::string(&conf, "operation")?;
    let run = ctx
        .pointer("/workflow/run_id")
        .and_then(Value::as_str)
        .ok_or("Missing admitted workflow identity")?;
    phases::progress("Processing verification phase");
    let result = phases::run(op, run, &conf, payload)?;
    let output =
        json!({"outputs":{"result":result},"status":"completed","artifacts":[],"metrics":{}});
    fs::write("/job/output.json", output.to_string()).map_err(|e| e.to_string())?;
    println!("{output}");
    Ok(())
}
fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}
