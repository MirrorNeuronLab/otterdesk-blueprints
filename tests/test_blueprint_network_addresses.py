"""Keep deployment-specific network addresses out of catalog payloads."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".py", ".sh", ".bash", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml", ".json"}
IPV4_LITERAL = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
IPV6_LITERAL = re.compile(r"\[([0-9a-fA-F:]+)\]")
NODE_ADDRESS = re.compile(r"\bmirror_neuron@[a-zA-Z0-9_.-]+")
PRIVATE_DNS_NAME = re.compile(r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:lan|home|internal|local)\b")
ALLOWED_PRIVATE_DNS = {"host.docker.internal", "mock.local"}


def _source_files(blueprint: str):
    root = ROOT / blueprint
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if relative.as_posix() == "config/default.json" or path.name == "package-lock.json":
            continue
        if any(part in {"tests", "test", "examples", "fixtures", "node_modules", "dist", ".claude"} for part in relative.parts):
            continue
        if path.name.startswith("test_"):
            continue
        yield path


def test_catalog_payloads_have_no_deployment_specific_addresses():
    violations = []
    for blueprint in json.loads((ROOT / "index.json").read_text(encoding="utf-8")):
        for path in _source_files(blueprint):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # Documentation comments and public source references do not set runtime hosts.
                if line.lstrip().startswith(("#", "//", "*")):
                    continue
                for match in IPV4_LITERAL.finditer(line):
                    try:
                        address = ipaddress.IPv4Address(match.group())
                    except ValueError:
                        continue
                    if not (address.is_loopback or address.is_unspecified):
                        violations.append((path, line_number, match.group()))
                for match in IPV6_LITERAL.finditer(line):
                    try:
                        address = ipaddress.IPv6Address(match.group(1))
                    except ValueError:
                        continue
                    if not (address.is_loopback or address.is_unspecified):
                        violations.append((path, line_number, match.group()))
                for pattern in (NODE_ADDRESS, PRIVATE_DNS_NAME):
                    for match in pattern.finditer(line):
                        if match.group().lower() not in ALLOWED_PRIVATE_DNS:
                            violations.append((path, line_number, match.group()))

    assert not violations, "Deployment-specific addresses belong in config/default.json:\n" + "\n".join(
        f"{path.relative_to(ROOT)}:{line_number}: {address}"
        for path, line_number, address in violations
    )
