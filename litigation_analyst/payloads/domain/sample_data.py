"""Explicit, pinned preparation of the public synthetic EMC2 demonstration corpus."""
import json
from pathlib import Path
import subprocess
import tempfile

EMC2_REPOSITORY = "https://github.com/jur1st/emc-2.git"
EMC2_REVISION = "6e2ecb0d0cd83eebe9b4ba6a3ce08f814d497977"


def prepare_emc2(destination):
    destination = Path(destination)
    marker = destination / ".mn-emc2.json"
    if destination.exists():
        if not marker.is_file() or json.loads(marker.read_text()) != {"repository": EMC2_REPOSITORY, "revision": EMC2_REVISION}:
            raise ValueError("existing sample folder has no matching EMC2 preparation record")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="emc2-", dir=destination.parent) as directory:
        staged = Path(directory) / "corpus"
        subprocess.run(["git", "init", "--quiet", str(staged)], check=True, timeout=30)
        subprocess.run(["git", "-C", str(staged), "fetch", "--quiet", "--depth=1", EMC2_REPOSITORY, EMC2_REVISION], check=True, timeout=300)
        subprocess.run(["git", "-C", str(staged), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True, timeout=30)
        revision = subprocess.check_output(["git", "-C", str(staged), "rev-parse", "HEAD"], text=True, timeout=10).strip()
        if revision != EMC2_REVISION or not (staged / "LICENSE.md").is_file():
            raise ValueError("EMC2 revision or license verification failed")
        (staged / marker.name).write_text(json.dumps({"repository": EMC2_REPOSITORY, "revision": revision}))
        staged.rename(destination)
    return destination
