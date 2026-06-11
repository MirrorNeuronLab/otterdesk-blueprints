from pathlib import Path
import json


BLUEPRINT_DIR = Path(__file__).resolve().parents[1]
DESIGNS_DIR = BLUEPRINT_DIR / "input" / "designs"


def test_design_templates_use_children_book_palette():
    card = (DESIGNS_DIR / "card_email.html").read_text()
    reply = (DESIGNS_DIR / "personal_reply.html").read_text()

    for color in ("#f24f5f", "#ffcf33", "#2f86c6"):
        assert color in card
    assert "#ecebe7" not in card
    assert "#ecebe7" not in reply

    assert "Story moments to explore" in card
    assert "Manage preferences" not in reply
    assert "Unsubscribe" not in reply
    assert "data-slot=\"body_section\"" in reply


def test_payload_design_copies_match_root_designs():
    root_card = (DESIGNS_DIR / "card_email.html").read_text()
    root_reply = (DESIGNS_DIR / "personal_reply.html").read_text()
    copied_designs = sorted((BLUEPRINT_DIR / "payloads").glob("*/input/designs"))

    assert copied_designs
    for designs_dir in copied_designs:
        assert (designs_dir / "card_email.html").read_text() == root_card
        assert (designs_dir / "personal_reply.html").read_text() == root_reply


def test_newsletter_templates_use_card_email_design():
    templates_dir = BLUEPRINT_DIR / "input" / "templates"

    for template_path in sorted(templates_dir.glob("*.json")):
        template = json.loads(template_path.read_text())
        template_id = template["template_id"]
        if template_id == "personal_reply":
            assert template["design_template"] == "personal_reply.html"
        else:
            assert template["design_template"] == "card_email.html"
