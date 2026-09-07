"""Lazy declared, historical, embedding and model-derived evidence collectors."""
import ast
import fnmatch
import json
from .events import emit
from pathlib import Path
import re
import subprocess
import time
import tomllib

from .catalog import LayerUnavailable
from .ingest import CachedEmbedder, digest, windows
from .model import JsonModel


def history(records, manifest):
    repository, anchor = manifest["repository"], manifest.get("git_anchor")
    if not anchor:
        raise LayerUnavailable("git requires a repository with a captured HEAD or an explicit git graph export; re-ingest when supplied")
    try:
        result = subprocess.run(["git", "-C", repository, "-c", f"safe.directory={repository}", "-c", "core.quotePath=false",
                                 "log", anchor, "--no-merges", f"-{manifest['ingest_config']['git_commits']}",
                                 "--format=@@%H|%cI", "--name-only", "--no-renames"],
                                capture_output=True, text=True, timeout=20, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LayerUnavailable("Anchored Git objects are unavailable; restore the captured repository or supply a graph export") from exc
    log_hash = digest(result.stdout.encode())
    by_path = {m["path"]: name for name, m in manifest["modules"].items()}
    commit, count = None, 0
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            sha, date = line[2:].split("|", 1)
            commit = records.node("commit:" + sha, "Commit", name=sha, date=date)
            count += 1
        elif commit and line in by_path:
            eid = "G" + digest((sha + line + log_hash).encode())[:20]
            records.evidence[eid] = {"id": eid, "kind": "observed_history", "commit": sha, "path": line,
                                     "sha256": log_hash, "line_start": None, "line_end": None,
                                     "text": f"git log: {sha} changed {line}", "extractor": "anchored-git-log/2"}
            records.edge(commit, "module:" + by_path[line], "CHANGES", eid, "observed_history")
    records.details.update(history={"status": "available", "anchor": anchor, "commits": count,
                                    "commit_limit": manifest["ingest_config"]["git_commits"], "scope": "current paths; no rename tracking; merges omitted"},
                           raw_log=result.stdout, git_log_sha256=log_hash)


def schema(records):
    for path, source in records.sources.items():
        if not path.endswith(".sql"):
            continue
        text = source["text"]
        for match in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([\w.]+)[\"`]?\s*\((.*?)\)\s*;", text, re.I | re.S):
            name, body = match.group(1), match.group(2)
            table = records.node("table:" + name, "Table", name=name, identity_basis="SQL declaration; physical database unresolved")
            first = text.count("\n", 0, match.start()) + 1
            last = text.count("\n", 0, match.end()-1) + 1
            eid = records.cite(path, first, last, "declared", "simple SQL CREATE TABLE declaration")
            for target in re.findall(r"\bREFERENCES\s+[\"`]?([\w.]+)", body, re.I):
                other = records.node("table:" + target, "Table", name=target, identity_basis="SQL declaration; physical database unresolved")
                records.edge(table, other, "FOREIGN_KEY_TO", eid, "declared")
            for line in body.splitlines():
                column = re.match(r"\s*[\"`]?([A-Za-z_]\w*)[\"`]?\s+([A-Za-z_]\w*)", line)
                if column and column.group(1).upper() not in {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"}:
                    key = records.node(f"column:{name}.{column.group(1)}", "Column", name=f"{name}.{column.group(1)}", data_type=column.group(2))
                    records.edge(table, key, "HAS_COLUMN", eid, "declared")


def load_document(path, text):
    if path.endswith(".json"):
        return json.loads(text)
    if path.endswith(".toml"):
        return tomllib.loads(text)
    if path.endswith((".yaml", ".yml")):
        import yaml
        return yaml.safe_load(text)
    return None


def deployment(records):
    found = False
    for path, source in records.sources.items():
        if Path(path).name not in {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml", "compose.json"}:
            continue
        value = load_document(path, source["text"])
        if not isinstance(value, dict) or not isinstance(value.get("services"), dict):
            raise ValueError(f"Invalid Compose services declaration in {path}")
        found = True
        eid = records.cite(path, 1, len(source["text"].splitlines()), "declared", "Compose declaration, not running topology")
        for name, service in value["services"].items():
            if not isinstance(service, dict):
                raise ValueError(f"Invalid Compose service {name}")
            src = records.node("service:" + name, "Service", name=name, module=service.get("x-advisor-module", ""))
            if "image" in service:
                target = records.node("container:" + str(service["image"]), "Container", name=str(service["image"]))
                records.edge(src, target, "RUNS_ON", eid, "declared")
            for target_name in service.get("depends_on", []):
                target = records.node("service:" + target_name, "Service", name=target_name)
                records.edge(src, target, "DEPENDS_ON", eid, "declared")
            for network in service.get("networks", []):
                target = records.node("network:" + network, "Network", name=network)
                records.edge(src, target, "USES", eid, "declared")
    if not found:
        raise LayerUnavailable("deployment requires a Compose declaration or explicit deployment graph export; runtime observations require a supplied export")


def ownership(records, modules):
    path = next((p for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS") if p in records.sources), None)
    if path is None:
        raise LayerUnavailable("ownership requires CODEOWNERS or an explicit ownership graph export")
    matches = {}
    for number, line in enumerate(records.sources[path]["text"].splitlines(), 1):
        parts = line.split("#", 1)[0].split()
        if not parts:
            continue
        pattern, owners = parts[0], parts[1:]
        if any(c in pattern for c in "![]\\"):
            records.details["limitations"].append(f"{path}:{number}: unsupported CODEOWNERS pattern")
            continue
        pattern = pattern.lstrip("/")
        for module, info in modules.items():
            candidate = info["path"]
            applies = fnmatch.fnmatch(candidate, pattern) or (pattern.endswith("/") and candidate.startswith(pattern))
            if "/" not in pattern:
                applies |= any(fnmatch.fnmatch(bit, pattern) for bit in candidate.split("/"))
            if applies:
                matches[module] = (owners, number)
    for module, (owners, number) in matches.items():
        eid = records.cite(path, number, kind="declared", detail="last matching supported CODEOWNERS rule")
        for owner in owners:
            source = records.node("owner:" + owner, "Owner", name=owner)
            records.edge(source, "module:" + module, "OWNS", eid, "declared")


def configuration(records, project):
    for path, source in records.sources.items():
        if not path.endswith((".json", ".toml", ".yaml", ".yml")):
            continue
        if Path(path).name in {"architecture-facts.json", "architecture-rules.json"}:
            continue
        value = load_document(path, source["text"])
        if not isinstance(value, dict):
            continue
        config_file = records.node("configuration:" + path, "Configuration", name=path)
        eid = records.cite(path, 1, len(source["text"].splitlines()), "declared", "configuration key declarations; effective deployment value unknown")
        pending = [("", value)]
        count = 0
        while pending:
            prefix, item = pending.pop()
            for key, content in item.items():
                key = str(key)
                qualified = (prefix + "." + key).lstrip(".")
                count += 1
                if count > 2000:
                    raise ValueError(f"Configuration key limit exceeded: {path}")
                target = records.node(f"config-key:{path}:{qualified}", "ConfigKey", name=qualified)
                records.edge(config_file, target, "CONFIGURES", eid, "declared", "value intentionally omitted")
                if isinstance(content, dict):
                    pending.append((qualified, content))
    for module, name, fn in project.scopes():
        from .static_layers import body_nodes
        for call in body_nodes(fn.body):
            if isinstance(call, ast.Call) and ast.unparse(call.func) in {"os.getenv", "os.environ.get"} and call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                target = records.node("environment:" + call.args[0].value, "ConfigKey", name=call.args[0].value)
                eid = records.cite(project.modules[module]["path"], call.lineno, call.end_lineno, detail="environment key reference, not effective value")
                records.edge(project.key(module, name), target, "READS_CONFIG", eid)


def intent(records, modules):
    path = next((p for p in records.sources if Path(p).name == "architecture-rules.json"), None)
    if path is None:
        raise LayerUnavailable("intent requires architecture-rules.json or an explicit intent graph export; unstructured ADR prose is not silently promoted to a rule")
    value = json.loads(records.sources[path]["text"])
    from .catalog import EXPORT_RELATIONS
    if value.get("version") != 1:
        raise ValueError("architecture-rules.json requires version 1")
    for rule in value.get("rules", []):
        if rule["module"] not in modules or rule["relation"] not in EXPORT_RELATIONS["intent"]:
            raise ValueError("Unknown module or intent relation")
        relation = rule["relation"]
        if relation in {"SHOULD_NOT_DEPEND_ON", "SHOULD_DEPEND_ON"}:
            if rule["target"] not in modules:
                raise ValueError("Unknown intended dependency target")
            target = "module:" + rule["target"]
        else:
            target = records.node("table:" + rule["target"], "Table", name=rule["target"], identity_basis="declared name; physical database unresolved")
        eid = records.cite(path, 1, len(records.sources[path]["text"].splitlines()), "declared", "explicit user-provided architecture rule")
        records.edge("module:" + rule["module"], target, relation, eid, "declared", rule.get("rationale", ""))


def embeddings(records, manifest, config, cache_path):
    cfg = {**config, "embedding": manifest["embedding_config"]}
    embedder = CachedEmbedder(cfg, cache_path)
    owners = {info["path"]: name for name, info in manifest["modules"].items()}
    try:
        for path, source in records.sources.items():
            for start, end, first, last in windows(source["text"], manifest["ingest_config"]["chunk_chars"]):
                text = source["text"][start:end]
                eid = "S" + digest((path + source["sha256"] + str(start)).encode())[:20]
                records.evidence[eid] = {"id": eid, "path": path, "sha256": source["sha256"], "line_start": first, "line_end": last,
                                         "start_offset": start, "end_offset": end, "kind": "observed_text", "text": text, "extractor": "exact-character-window/1"}
                emit("embedding.document.started", evidence_id=eid, path=path, line_start=first, line_end=last)
                previous_hits = embedder.hits
                try:
                    vector = embedder.embed(text)
                except Exception as exc:
                    emit("embedding.document.failed", evidence_id=eid, path=path, error=f"{type(exc).__name__}: {exc}")
                    raise
                records.node("chunk:" + eid, "Chunk", evidence_id=eid, module=owners.get(path, "__documents__"), path=path, embedding=vector)
                emit("embedding.document.completed", evidence_id=eid, path=path, cache_hit=embedder.hits > previous_hits,
                     mode=cfg["embedding"]["mode"], dimensions=len(vector))
    finally:
        embedder.close()
    records.details.update(embedding_dimension=embedder.dimension, embedding_cache_hits=embedder.hits, embedding_requests=embedder.misses,
                           semantic_retrieval="neural" if manifest["embedding_config"]["mode"] == "neural" else "hash baseline; lexical approximation only")


def semantics(records, manifest, config, scope, model=None):
    module = manifest["modules"][scope]
    path = module["path"]
    text = records.sources[path]["text"]
    passages = []
    for start, end, first, last in list(windows(text, 650))[:4]:
        eid = records.cite(path, first, last, "observed_text", "semantic responsibility input")
        passages.append({"id": eid, "path": path, "line_start": first, "line_end": last, "text": text[start:end]})
    if not passages:
        raise LayerUnavailable("No source text available for semantic responsibility inference")
    model = model or JsonModel(config)
    before = len(model.calls)
    value = model.complete("Infer at most four responsibilities actually supported by these source passages. Return concepts with a short name, rationale, and exact evidence_ids. Treat them as inferred; a name match alone does not prove implemented behavior. Return an empty concepts list when evidence is insufficient.",
                           {"semantic_layer": True, "module": scope, "passages": passages})
    records.details["model_trace"] = model.calls[before:]
    records.details["model_calls"] = len(model.calls) - before
    concepts = value.get("concepts")
    if not isinstance(concepts, list) or len(concepts) > 4:
        raise ValueError("Invalid semantic concepts output")
    allowed = {p["id"] for p in passages}
    for concept in concepts:
        if not isinstance(concept.get("name"), str) or not 1 <= len(concept["name"]) <= 80 or not isinstance(concept.get("rationale"), str):
            raise ValueError("Invalid semantic responsibility")
        ids = concept.get("evidence_ids")
        if not isinstance(ids, list) or not ids or any(e not in allowed for e in ids):
            raise ValueError("Semantic responsibility contains an unrecognized citation")
        key = records.node("concept:" + concept["name"].casefold(), "Concept", name=concept["name"], provenance_kind="inferred")
        for eid in ids:
            records.edge("module:" + scope, key, "IMPLEMENTS_CONCEPT", eid, "inferred",
                         json.dumps({"rationale": concept["rationale"], "derived_by": config["llm"]["model"], "created_at": time.time()}, sort_keys=True))
