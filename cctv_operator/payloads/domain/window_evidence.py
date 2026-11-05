"""Interpret explicit model assessments and render only boxes grounded on the saved image."""

import base64
import io
import json
import re

from PIL import Image, ImageDraw

from .settings import DEFAULT_PROMPT


def window_prompt(goal):
    if goal == DEFAULT_PROMPT:
        return goal
    return (
        "Describe the visible scene even when the target is absent. Assess the exact condition below, "
        "including negation. Use matched only when the requested condition is visible. Use uncertain "
        "for obscured details. To report a missing item, its wearer or location must be visible. "
        'Return only one JSON object {"verdict":"matched|not_matched|uncertain","summary":"one concise sentence"}. '
        "Monitoring goal: " + goal
    )


def assessment(content):
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    try:
        result = json.loads(fenced[1] if fenced else text)
    except ValueError:
        result = None
    if isinstance(result, dict) and isinstance(result.get("summary"), str) and result["summary"].strip():
        verdict = result.get("verdict")
        return (verdict if verdict in ("matched", "not_matched", "uncertain") else "uncertain",
                result["summary"].strip(), result.get("bbox_2d"))
    # Free prose and legacy bbox snippets are never affirmative verdicts.
    prose = text.split("```", 1)[0].strip()
    return "uncertain", (prose if prose and not prose.startswith(("{", "[")) else
                         "The model did not return a readable observation."), None


def box_coordinates(value):
    if (isinstance(value, list) and len(value) == 4 and all(type(n) is int for n in value)
            and 0 <= value[0] < value[2] <= 1000 and 0 <= value[1] < value[3] <= 1000
            and value != [0, 0, 1000, 1000]):
        return value
    return None


def display_frame(jpeg, box, *, thumbnail=False):
    if not box and not thumbnail:
        return jpeg
    with Image.open(io.BytesIO(jpeg)) as image:
        if box:
            size = (image.width - 1, image.height - 1) * 2
            ImageDraw.Draw(image).rectangle([round(n * scale / 1000) for n, scale in zip(box, size)],
                                            outline="#ffd34d", width=max(2, image.width // 160))
        if thumbnail:
            image.thumbnail((480, 320))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=72)
        return out.getvalue()


def chat_frame(caption, jpeg, box=None):
    thumbnail = display_frame(jpeg, box, thumbnail=True)
    if len(thumbnail) <= 75 * 1024:
        return {"run_id": caption["run_id"], "mime_type": "image/jpeg",
                "data": base64.b64encode(thumbnail).decode("ascii"), "title": "Window snapshot",
                "alt": f"{caption.get('camera', 'Camera')} preview received during the video window",
                "caption": f"Preview received {caption['snapshot']['received_at']} during this window."
                           + (" Box estimated on this image." if box else "")}
