"""Fixtures exercise the converted domain inside an SDK-shaped artifact boundary."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'software_architecture_advisor'
RGX = Path(os.environ.get('ADVISOR_RGX_BINARY', '/not-installed/rgx'))


def configuration():
    from domain.config import validate_config, offline_config
    cfg = validate_config(json.loads((ROOT / 'config/default.json').read_text()))
    cfg = offline_config(cfg)
    cfg['graph']['binary'] = str(RGX)
    return cfg
