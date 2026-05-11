import json

def extract_payload(message: dict) -> dict:
    body = message.get("body") or {}
    if isinstance(body, dict) and isinstance(body.get("sandbox"), dict):
        stdout = (body.get("sandbox", {}).get("stdout") or "").strip()
        if stdout:
            # find the last line that looks like json
            for line in reversed(stdout.split('\n')):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        return json.loads(line)
                    except:
                        pass
    return body
