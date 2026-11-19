"""Download and verify the vendor files referenced by the bundled USD stage."""

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def fetch(root, relative, asset):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid relative asset path: {relative}")
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        for attempt in range(3):
            try:
                digest = hashlib.sha256()
                with urlopen(asset["url"], timeout=120) as response, partial.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                if partial.stat().st_size != asset["size"] or digest.hexdigest() != asset["sha256"]:
                    raise ValueError(f"OpenUSD asset failed verification: {relative}")
                partial.replace(destination)
                return
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    finally:
        partial.unlink(missing_ok=True)


def main(lock, output):
    assets = json.loads(Path(lock).read_text())
    root = Path(output)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, root, name, asset) for name, asset in assets.items()]
        for future in futures:
            future.result()
    print(f"Verified {len(assets)} OpenUSD dependencies.", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
