"""Financial playbook discovery and bounded actor context."""

from .common import *

def load_prompt(name: str) -> str:
    return PROMPTS.load(name)

def render_prompt(name: str, **values: str) -> str:
    return PROMPTS.render(name, **values)

def financial_knowledge_search_roots(blueprint_dir: Path) -> list[Path]:
    roots = [blueprint_dir, blueprint_dir / "payloads"]
    bundle_dir = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle_dir:
        roots.append(Path(bundle_dir).expanduser())
    script_path = Path(__file__).resolve()
    roots.extend([script_path.parents[1], script_path.parents[2], script_path.parents[3]])
    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots

def load_financial_knowledge(blueprint_dir: Path) -> dict[str, Any]:
    playbook_path = next(
        (
            root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH
            for root in financial_knowledge_search_roots(blueprint_dir)
            if (root / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH).exists()
        ),
        blueprint_dir / KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
    )
    try:
        content = playbook_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    return {
        "id": "financial_advisor_playbook",
        "title": "Financial Advisor Evidence And Review Playbook",
        "path": KNOWLEDGE_PLAYBOOK_RELATIVE_PATH,
        "resolved_path": str(playbook_path),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
        "content": content[:24000],
        "judge_rubric": list(FINANCIAL_JUDGE_RUBRIC),
        "domain_guard": "Use financial-advisor knowledge for review-only household finance, tax intake, and portfolio risk analysis; do not turn it into personalized execution advice.",
    }

def financial_knowledge_reference(active_knowledge: dict[str, Any] | None) -> dict[str, Any]:
    knowledge = active_knowledge or {}
    return {
        "id": knowledge.get("id"),
        "title": knowledge.get("title"),
        "path": knowledge.get("path"),
        "sha256": knowledge.get("sha256"),
        "judge_rubric": list(knowledge.get("judge_rubric") or FINANCIAL_JUDGE_RUBRIC),
        "domain_guard": knowledge.get("domain_guard"),
    }

def _knowledge_sections(content: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
            continue
        if not line.startswith("# "):
            current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return [section for section in sections if section["content"]]

def knowledge_context_for_step(active_knowledge: dict[str, Any] | None, step_id: str, *, max_chars: int = 9000) -> dict[str, Any]:
    knowledge = active_knowledge or {}
    content = str(knowledge.get("content") or "")
    terms = tuple(term.lower() for term in KNOWLEDGE_SECTIONS_BY_STEP.get(step_id, ("evidence hierarchy", "review boundary", "report quality")))
    matched = [
        section
        for section in _knowledge_sections(content)
        if any(term in section["title"].lower() for term in terms)
    ]
    if not matched:
        matched = _knowledge_sections(content)[:2]
    selected: list[dict[str, str]] = []
    used_chars = 0
    for section in matched:
        remaining = max_chars - used_chars
        if remaining <= 80:
            break
        section_content = section["content"][:remaining]
        selected.append({"title": section["title"], "content": section_content})
        used_chars += len(section_content)
    return {
        "playbook": financial_knowledge_reference(knowledge),
        "sections": selected,
        "judge_rubric": list(knowledge.get("judge_rubric") or FINANCIAL_JUDGE_RUBRIC),
        "retrieval_status": "static_blueprint_playbook" if selected else "unavailable",
        "instruction": "Treat this as domain guidance. Apply only when supported by the supplied artifacts; label unknowns and assumptions instead of filling gaps.",
    }
