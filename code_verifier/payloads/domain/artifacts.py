"""Editable rules and investigation checkpoints in the contained run workspace."""
from mn_sdk.blueprint_support import write_json
from mn_sdk_common.files import atomic_write_text


def save(block, name, value):
    write_json(block.store.path(name), value)


def read(block, name):
    return block.store.read_path(name)


def text(block, name, value):
    target = block.store.path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, value, mode=0o644)
