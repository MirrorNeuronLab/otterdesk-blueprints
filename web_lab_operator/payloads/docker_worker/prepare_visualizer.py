"""Image-build assets for the pinned PyLabRobot visualizer; never run by a worker."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def prepare(destination):
    manifest = json.loads(Path(__file__).with_name('visualizer-assets.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for item in manifest.values():
        with urlopen(item['url'], timeout=30) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('The pinned visualizer dependency failed integrity verification.')
        path = destination / item['file']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (destination / 'assets.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    prepare(Path('/opt/web-lab/visualizer-vendor'))
