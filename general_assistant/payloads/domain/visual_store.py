"""Private Computer Use images and bounded locators; Membrane owns the index."""
import hashlib
import json
import math
import re

from mn_sdk.blueprint.hooks import fingerprint
from mn_context_engine_sdk import MediaReference
from mn_sdk.blueprint.storage import file_transaction
from mn_sdk_common.files import atomic_write_bytes, atomic_write_json

PRINCIPAL = "computer-use-visual"


class VisualStore:
    def __init__(self, block, limits):
        directory = block.job_directory
        self.identity = {"job_id": block.job_id, "principal": PRINCIPAL}
        self.key = fingerprint(self.identity)
        self.root = directory / "state" / "computer_use_visual"
        if not self.root.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Visual memory must remain inside its Job directory")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "catalog.json"
        self.limits = limits
        self.entries()

    def _read(self):
        if self.path.is_symlink() or (self.root / "images").is_symlink():
            raise ValueError("Visual memory requires original private Job files")
        if not self.path.exists():
            return {"version": 1, "identity": self.identity, "entries": []}
        if self.path.stat().st_size > 1024 * 1024:
            raise ValueError("Visual memory catalog exceeds its bound")
        value = json.loads(self.path.read_text())
        if (not isinstance(value, dict) or value.get("version") != 1 or value.get("identity") != self.identity
                or not isinstance(value.get("entries"), list) or len(value["entries"]) > 128):
            raise ValueError("Visual memory catalog belongs to another Job or is invalid")
        for row in value["entries"]:
            self._validate(row)
        if len({row["id"] for row in value["entries"]}) != len(value["entries"]):
            raise ValueError("Visual memory has duplicate identities")
        return value

    def _validate(self, row):
        keys = {"id", "app_bundle_id", "targets", "run_id", "observed_at", "media", "catalog", "model_identity"}
        if (not isinstance(row, dict) or set(row) != keys
                or not isinstance(row["app_bundle_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,199}", row["app_bundle_id"])
                or not isinstance(row["run_id"], str) or not 0 < len(row["run_id"]) <= 160
                or type(row["observed_at"]) not in {int, float} or not math.isfinite(row["observed_at"])
                or not isinstance(row["targets"], list) or len(row["targets"]) > 16):
            raise ValueError("Visual memory locator is invalid")
        for target in row["targets"]:
            if (not isinstance(target, dict) or set(target) != {"role", "label"}
                    or target["role"] not in {"AXTextField", "AXTextArea", "AXComboBox"}
                    or not isinstance(target["label"], str) or not 0 < len(target["label"]) <= 160):
                raise ValueError("Visual memory field hint is invalid")
        reference = MediaReference.from_dict(row["media"])
        if (reference.uri != self.uri(reference.sha256) or reference.mime_type != "image/jpeg"
                or reference.size_bytes > 4 * 1024 * 1024
                or row["id"] != fingerprint([self.key, row["app_bundle_id"], row["media"], row["targets"]])):
            raise ValueError("Visual memory image identity changed")
        catalog, model = row["catalog"], row["model_identity"]
        if catalog is not None and (not isinstance(catalog, dict) or not isinstance(catalog.get("sources"), list)
                                    or len(catalog["sources"]) != 1 or not isinstance(catalog["sources"][0], dict)):
            raise ValueError("Visual memory source catalog is invalid")
        if model is not None and (not isinstance(model, list) or len(model) != 3
                or any(not isinstance(v, str) or not 0 < len(v) <= 1024 for v in model[:2])
                or type(model[2]) is not int or not 0 < model[2] <= 4096):
            raise ValueError("Visual memory embedding identity is invalid")

    def entries(self):
        with file_transaction(self.path):
            return self._read()["entries"]

    def uri(self, sha256):
        return f"artifact://computer-use-visual/{self.key}/{sha256}.jpg"

    def load_image(self, reference):
        if reference.uri != self.uri(reference.sha256) or reference.mime_type != "image/jpeg":
            raise ValueError("Visual image reference is outside this Job")
        path = self.root / "images" / (reference.sha256 + ".jpg")
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Visual image must be an original private asset")
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Visual image exceeds its capture bound")
        data = path.read_bytes()
        reference.verify(data)
        return data

    def reserve(self, state, *, run_id, observed_at):
        data = state["image"]
        if not isinstance(data, bytes) or not 0 < len(data) <= 4 * 1024 * 1024:
            raise ValueError("Visual memory requires a bounded original JPEG capture")
        reference = MediaReference.from_bytes(data, uri=self.uri(hashlib.sha256(data).hexdigest()), mime_type="image/jpeg")
        identity = fingerprint([self.key, state["app_bundle_id"], reference.to_dict(), state["targets"]])
        with file_transaction(self.path):
            catalog = self._read()
            prior = next((row for row in catalog["entries"] if row["id"] == identity), None)
            if prior:
                self.load_image(reference)
                return prior
            image_dir = self.root / "images"
            assets = list(image_dir.glob("*.jpg"))
            if len(assets) > 128 or any(path.is_symlink() for path in assets):
                raise ValueError("Visual assets must be original private files")
            path = image_dir / (reference.sha256 + ".jpg")
            size = sum(asset.stat().st_size for asset in assets) + (0 if path.exists() else len(data))
            if len(catalog["entries"]) >= self.limits["max_images"] or size > self.limits["max_bytes"]:
                return None
            if path.exists():
                self.load_image(reference)
            else:
                atomic_write_bytes(path, data, create_parents=True)
            row = {"id": identity, "app_bundle_id": state["app_bundle_id"], "targets": state["targets"],
                   "run_id": run_id, "observed_at": observed_at, "media": reference.to_dict(),
                   "catalog": None, "model_identity": None}
            catalog["entries"].append(row)
            atomic_write_json(self.path, catalog)
            return row

    def update(self, row):
        with file_transaction(self.path):
            catalog = self._read()
            prior = next((value for value in catalog["entries"] if value["id"] == row["id"]), None)
            if prior is None or any(prior[key] != row[key] for key in prior if key not in {"catalog", "model_identity"}):
                raise ValueError("Immutable visual memory identity changed")
            catalog["entries"] = [row if value["id"] == row["id"] else value for value in catalog["entries"]]
            atomic_write_json(self.path, catalog)
