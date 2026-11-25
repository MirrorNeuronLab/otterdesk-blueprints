"""Build the verifier and its WIT skills, then refresh the five self-contained packages."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

CATALOG = Path(__file__).resolve().parent.parent
WORKER = CATALOG / "verifier-wasm"
BLUEPRINTS = ("software_verifier_suite", "functional_verifier", "compatibility_verifier",
              "security_verifier", "reliability_verifier")
SKILLS = ("code_search_skill_wit", "comparison_evidence_skill_wit", "folder_files_skill_wit",
          "static_code_analysis_skill_wit", "verification_checks_skill_wit", "web_report_skill_wit")


def build(skills, build_dir):
    interface = skills / "wit/skills.wit"
    if interface.read_bytes() != (WORKER / "wit/deps/skills/skills.wit").read_bytes():
        raise ValueError("The verifier WIT import differs from the skills interface")
    for manifest in (skills / "Cargo.toml", WORKER / "Cargo.toml"):
        subprocess.run(["cargo", "+1.100.0", "build", "--locked", "--release",
                        "--target", "wasm32-wasip3", "--manifest-path", str(manifest),
                        "--target-dir", str(build_dir)], check=True)
    built = build_dir / "wasm32-wasip3/release"
    artifacts = {name: (built / (name + ".wasm")).read_bytes() for name in SKILLS}
    agent = built / "software-verifier-worker.wasm"
    # Type-check the complete composition before modifying a catalog package.
    command = ["wac", "plug", str(agent)]
    for name in SKILLS:
        command.extend(["--plug", str(built / (name + ".wasm"))])
    subprocess.run([*command, "-o", str(build_dir / "checked.wasm")], check=True)
    phase_agent = built / "verifier-phases.wasm"
    subprocess.run([command[0], command[1], str(phase_agent), *command[3:], "-o",
                    str(build_dir / "checked-phases.wasm")], check=True)
    for bp in BLUEPRINTS:
        package = CATALOG / bp
        deps = package / "dependencies.json"
        declared = json.loads(deps.read_text())
        entries = {d["name"]: d for d in declared["skills"] if d["type"] == "wit"}
        if entries.keys() != artifacts.keys():
            raise ValueError(f"Unexpected WIT dependency set in {bp}")
        for name, data in artifacts.items():
            entry = entries[name]
            target = f"wasm/skills/{name}.wasm"
            if entry["path"] != target:
                raise ValueError(f"Unexpected skill path in {bp}")
            (package / "payloads" / target).write_bytes(data)
            entry["sha256"] = sha256(data).hexdigest()
        shutil.copyfile(agent, package / "payloads/wasm/verifier.wasm")
        shutil.copyfile(phase_agent, package / "payloads/wasm/verifier-phases.wasm")
        shutil.copyfile(WORKER / "bindings.py", package / "payloads/domain/wit_verification.py")
        deps.write_text(json.dumps(declared, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", type=Path, required=True, help="mn-skills checkout")
    parser.add_argument("--target-dir", type=Path, help="persistent Cargo build directory")
    args = parser.parse_args()
    if args.target_dir:
        build(args.skills.resolve(), args.target_dir.resolve())
    else:
        with TemporaryDirectory(prefix="verifier-wasi-") as temporary:
            build(args.skills.resolve(), Path(temporary))


if __name__ == "__main__":
    main()
