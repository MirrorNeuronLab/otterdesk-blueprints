"""Publish the verified specification catalog, evidence registers and proposed work."""

from datetime import datetime, timezone
from .catalog_store import CatalogStore, fingerprint
from .catalog_contract import load_catalog, load_snapshot
from .review_response import validate_result
from .review_prompts import requirements
from .review_packets import chunk_snapshot
from .catalog_planning import catalog_settings


def assemble(context, *, llm_client=None):
    store = CatalogStore(context["run_dir"])
    saved = store.read("catalog/context.json")
    plan = store.load_ref(saved["plan"])
    terminal = store.read("catalog/terminal.json")
    review, _ = catalog_settings(context["config"])
    catalog = load_catalog()
    snapshot = load_snapshot(context["run_dir"])
    if (
        catalog["digest"] != plan["catalog_digest"]
        or fingerprint(snapshot["manifest"]) != saved["request"]["snapshot"]
    ):
        raise ValueError("Publication snapshot/catalog mismatch")
    results = store.results()
    packets = {
        p["packet_id"]: p for p in chunk_snapshot(snapshot, review["chunk_bytes"])
    }
    for ident, value in results.items():
        task = store.read(f"catalog/tasks/{ident}.json")
        request = store.read(f"catalog/requests/{ident}.json")
        if value["request_hash"] != fingerprint(request):
            raise ValueError("Publication request hash mismatch")
        validate_result(
            {**task, "input_task_ids": request["input_task_ids"]},
            value,
            snapshot,
            packets,
            request["requirements"],
            list(request["evidence"].values()),
        )
    evidence = {}
    claims = {}
    claim_map = {}
    findings = {}
    for ident, value in sorted(results.items()):
        if value["status"] != "completed":
            continue
        for observation in value.get("observations", []):
            for c in observation["evidence"]:
                eid = "E-" + fingerprint(c)[:16]
                evidence[eid] = {
                    "id": eid,
                    **c,
                    "snapshot": snapshot["snapshot_id"],
                    "revision": snapshot["manifest"].get("git_anchor"),
                }
        for c in value.get("claims", []):
            eids = []
            for citation in c["evidence"]:
                eid = "E-" + fingerprint(citation)[:16]
                eids.append(eid)
                evidence[eid] = {
                    "id": eid,
                    **citation,
                    "snapshot": snapshot["snapshot_id"],
                    "revision": snapshot["manifest"].get("git_anchor"),
                }
            counter_ids = []
            for citation in c['counterevidence_citations']:
                eid = 'E-' + fingerprint(citation)[:16]
                counter_ids.append(eid)
                evidence[eid] = {'id':eid, **citation, 'snapshot':snapshot['snapshot_id'],
                                'revision':snapshot['manifest'].get('git_anchor')}
            canonical = {
                k: c[k]
                for k in [
                    "statement",
                    "claim_type",
                    "confidence",
                    "rationale",
                    "counterevidence",
                    "counterevidence_status",
                ]
            }
            canonical["evidence_ids"] = eids
            canonical['counterevidence_ids'] = counter_ids
            if 'architecture' in c:
                canonical['architecture'] = c['architecture']
            cid = "C-" + fingerprint(canonical)[:16]
            claim_map[(ident, c["claim_id"])] = cid
            record = claims.setdefault(
                cid, {"id": cid, **canonical, "source_tasks": []}
            )
            record["source_tasks"].append(ident)
            if c.get("finding"):
                fid = (
                    "F-"
                    + fingerprint(
                        {
                            "statement": c["statement"].strip().lower(),
                            "evidence": sorted(eids),
                            "counterevidence": sorted(counter_ids),
                            "counterevidence_status": c["counterevidence_status"],
                        }
                    )[:16]
                )
                finding = findings.setdefault(
                    fid,
                    {
                        "id": fid,
                        "statement": c["statement"],
                        "claim_ids": [],
                        "aspect_ids": [],
                        "evidence_ids": eids,
                        "counterevidence": c["counterevidence"],
                        "counterevidence_status": c['counterevidence_status'],
                        "counterevidence_ids": counter_ids,
                        "confidence": c["confidence"],
                        "confidence_rationale": c["rationale"],
                        "architecture": c.get('architecture'),
                    },
                )
                if cid not in finding["claim_ids"]:
                    finding["claim_ids"].append(cid)
                if (
                    value.get("aspect_id")
                    and value["aspect_id"] not in finding["aspect_ids"]
                ):
                    finding["aspect_ids"].append(value["aspect_id"])
    for finding in findings.values():
        verdicts = {
            aid: results.get("challenge-" + aid, {}).get(
                "analysis_verdict", "not_analyzed"
            )
            for aid in finding["aspect_ids"]
        }
        finding["challenge_verdicts"] = verdicts
        finding["status"] = (
            "contested"
            if "contradicted" in verdicts.values()
            else "supported"
            if verdicts and all(v == "supported" for v in verdicts.values())
            else "provisional"
        )
    coverage = []
    verifications = []
    for section in catalog["sections"]:
        for aid in section["aspect_ids"]:
            a = results.get("analysis-" + aid, {})
            challenge = results.get("challenge-" + aid, {})
            state = a.get(
                "coverage",
                "blocked" if a.get("status") == "blocked" else "not_analyzed",
            )
            if state == "complete_for_stated_scope" and (
                challenge.get("status") != "completed"
                or challenge.get("analysis_verdict") != "supported"
            ):
                state = "partial"
            reason = (
                a.get("applicability_reason")
                or a.get("reason")
                or "Task not executed before stop"
            )
            limits = a.get("limitations", []) + challenge.get("limitations", [])
            row = {
                "aspect_id": aid,
                "section": section["number"],
                "title": catalog["specs"][aid]["title"],
                "applicability": a.get("applicability", "undetermined"),
                "applicability_reason": reason,
                "coverage": state,
                "outcome": a.get("outcome", "undetermined"),
                "scope": a.get("scope", "No analyzed scope"),
                "challenge": challenge.get("analysis_verdict", "not_analyzed"),
                "limitations": limits,
                "requirement_count": len(requirements(catalog["specs"][aid])),
                "content": [
                    {
                        **item,
                        "claim_ids": [
                            claim_map[("analysis-" + aid, cid)]
                            for cid in item.get("claim_ids", [])
                        ],
                    }
                    for item in a.get("content", [])
                ],
                "analysis_task": "analysis-" + aid,
                "challenge_task": "challenge-" + aid,
            }
            coverage.append(row)
            if state != "complete_for_stated_scope":
                verifications.append(
                    {
                        "id": "V-" + aid,
                        "aspect_ids": [aid],
                        "claim_ids": [],
                        "question": catalog["specs"][aid]["question"],
                        "method": "Review the unresolved content requirements and counterevidence in the linked aspect task.",
                        "required_input": "; ".join(limits) or reason,
                        "acceptance": "Address every requirement with traceable evidence or a justified applicability decision.",
                        "status": "open",
                    }
                )
    recommendations = []
    assumptions = []
    packages = []
    for ident, value in sorted(results.items()):
        if value["status"] != "completed" or value["kind"] not in {
            "aspect_analysis",
            "aspect_challenge",
        }:
            continue
        aid = value["aspect_id"]
        challenge = results.get("challenge-" + aid, {})
        gate = challenge.get("analysis_verdict") != "supported"

        def refs(item):
            return [claim_map[(ident, c)] for c in item.get("claim_ids", [])]

        for i, item in enumerate(value.get("recommendations", [])):
            cids = refs(item)
            fids = [
                f["id"] for f in findings.values() if set(f["claim_ids"]) & set(cids)
            ]
            recommendations.append(
                {
                    **item,
                    "id": "R-" + fingerprint([ident, i, item])[:16],
                    "claim_ids": cids,
                    "finding_ids": fids,
                    "aspect_ids": [aid],
                    "status": "proposed",
                    "claim_type": "proposed",
                    "verification_required": gate,
                    "owner_status": "unassigned",
                    "confidence_basis": {c: claims[c]["confidence"] for c in cids},
                }
            )
        for i, item in enumerate(value.get("verification_tasks", [])):
            verifications.append(
                {
                    **item,
                    "id": "V-" + fingerprint([ident, i, item])[:16],
                    "claim_ids": refs(item),
                    "aspect_ids": [aid],
                    "status": "open",
                }
            )
        for i, item in enumerate(value.get("assumptions", [])):
            assumptions.append(
                {
                    **item,
                    "id": "A-" + fingerprint([ident, i, item])[:16],
                    "aspect_ids": [aid],
                    "status": "unverified",
                }
            )
        for i, item in enumerate(value.get("work_packages", [])):
            cids = refs(item)
            linked = [
                r["id"] for r in recommendations if set(r["claim_ids"]) & set(cids)
            ]
            if not linked:
                continue
            packages.append(
                {
                    **item,
                    "id": "W-" + fingerprint([ident, i, item])[:16],
                    "claim_ids": cids,
                    "recommendation_ids": linked,
                    "baseline": {
                        "snapshot": snapshot["snapshot_id"],
                        "revision": snapshot["manifest"].get("git_anchor"),
                    },
                    "evidence_ids": sorted(
                        {eid for c in cids for key in ("evidence_ids", "counterevidence_ids")
                         for eid in claims[c][key]}
                    ),
                    "status": "proposed",
                    "approval_status": "not_authorized_by_report",
                    "verification_required": gate,
                    "allowed_actions": "Review this proposal; implementation requires separately authorized scope.",
                    "completion_report": "Report changed files, reasoning, actual executed checks/results, unresolved risks and the next decision.",
                }
            )
    sections = []
    for section in catalog["sections"]:
        rows = [r for r in coverage if r["section"] == section["number"]]
        states = [r["coverage"] for r in rows]
        state = (
            "complete_for_stated_scope"
            if all(s == "complete_for_stated_scope" for s in states)
            else (
                "partial"
                if any(s in {"partial", "complete_for_stated_scope"} for s in states)
                else ("blocked" if "blocked" in states else "not_analyzed")
            )
        )
        applicability = (
            "not_applicable"
            if all(r["applicability"] == "not_applicable" for r in rows)
            else (
                "applicable"
                if any(r["applicability"] == "applicable" for r in rows)
                else "undetermined"
            )
        )
        sections.append(
            {
                **section,
                "coverage": state,
                "applicability": applicability,
                "reason": "Rollup of individual aspect decisions",
            }
        )
    scanned = {
        t["packet_id"]
        for t in plan["tasks"]
        if t["kind"] == "source_scan"
        and results.get(t["task_id"], {}).get("status") == "completed"
    }
    source_coverage = [
        {k: p[k] for k in ["packet_id", "path", "sha256", "start_offset", "end_offset"]}
        | {"coverage": "reviewed" if p["packet_id"] in scanned else "not_analyzed"}
        for p in plan["packet_index"]
    ]
    executive = results.get("executive", {})
    report = {
        "schema_version": "mn.architecture.catalog_report.v1",
        "status": "review_draft"
        if all(r["coverage"] == "complete_for_stated_scope" for r in coverage)
        and executive.get("status") == "completed"
        and not terminal["pending_task_ids"]
        else "partial",
        "snapshot": snapshot["snapshot_id"],
        "input": snapshot["manifest"].get("input", {}),
        "goal": saved["request"]["goal"],
        "analysis_started": datetime.fromtimestamp(
            saved["started"], timezone.utc
        ).isoformat(),
        "catalog_digest": catalog["digest"],
        "scope": {
            "source_files": len(snapshot["inventory"]),
            "source_packets": len(packets),
            "reviewed_source_packets": len(scanned),
            "capture_limits": snapshot["manifest"].get("coverage", {}),
            "exclusions": snapshot["manifest"]
            .get("ingest_config", {})
            .get("exclude", []),
            "method": "Frozen text, static dependency baseline, bounded OpenCode reviews, independent aspect challenges; no reviewed code executed.",
            "runtime_evidence": "not_collected",
            "history": "only captured immutable revision; no history measurement inferred",
        },
        "executive": executive.get(
            "conclusion",
            "Executive review was not completed; inspect explicit partial coverage.",
        ),
        "executive_claim_type": "inferred",
        "executive_source_tasks": executive.get("source_task_ids", []),
        "terminal": terminal,
        "sections": sections,
        "coverage": coverage,
        "findings": list(findings.values()),
        "counts": {
            "completed": sum(v["status"] == "completed" for v in results.values()),
            "blocked": sum(v["status"] == "blocked" for v in results.values()),
            "not_analyzed": sum(
                v["status"] == "not_analyzed" for v in results.values()
            ),
        },
        "authorization": "Proposals only. No source modification, deployment or operational action is authorized by this report.",
    }
    files = {
        "coverage": {
            "aspects": coverage,
            "sections": sections,
            "sources": source_coverage,
        },
        "evidence": list(evidence.values()),
        "claims": list(claims.values()),
        "findings": list(findings.values()),
        "recommendations": recommendations,
        "assumptions": assumptions,
        "verification_tasks": verifications,
        "work_packages": packages,
        "roadmap": {
            "status": "proposed" if packages else "undetermined",
            "stages": [
                {
                    "id": "M-" + p["id"][2:],
                    "work_package_id": p["id"],
                    "recommendation_ids": p["recommendation_ids"],
                    "steps": p["migration_steps"],
                    "gates": p["acceptance"],
                    "limitations": "Validate intermediate states, mixed versions, data authority and rollback/forward repair before approval.",
                }
                for p in packages
            ],
            "limitations": [
                "No migration is selected or authorized merely by generating this report."
            ],
        },
    }
    _validate_links(files)
    return report, files, results


def _validate_links(files):
    targets = {
        key: {r["id"] for r in files[key]}
        for key in ["claims", "evidence", "findings", "recommendations"]
    }
    for key in [
        "claims",
        "findings",
        "recommendations",
        "verification_tasks",
        "work_packages",
    ]:
        for item in files[key]:
            for field, target in [
                ("claim_ids", "claims"),
                ("evidence_ids", "evidence"),
                ("counterevidence_ids", "evidence"),
                ("finding_ids", "findings"),
                ("recommendation_ids", "recommendations"),
            ]:
                if not set(item.get(field, [])) <= targets[target]:
                    raise ValueError("Unresolvable report traceability link")
