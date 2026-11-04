#!/usr/bin/env python3
"""Validate configuration without contacting a camera or printing its address."""
import json
import os
from urllib.parse import urlsplit


def main():
    try:
        config = json.loads(os.environ.get('MN_BLUEPRINT_CONFIG_JSON', '{}'))
        uri = config.get('video_source', {}).get('uri', '')
        if not isinstance(uri, str) or not 8 <= len(uri) <= 2048 or any(ord(c) < 32 or ord(c) == 127 for c in uri):
            raise ValueError()
        parts = urlsplit(uri.strip())
        if parts.scheme not in {'rtsp', 'rtsps'} or not parts.hostname or parts.fragment:
            raise ValueError()
        parts.port
    except (ValueError, TypeError, AttributeError):
        print(json.dumps({'ok': False, 'issues': [{'code': 'camera_configuration', 'message': 'Enter an approved RTSP or RTSPS URL in the secure Video stream URL field.'}]}))
        return 1
    print(json.dumps({'ok': True, 'issues': [], 'message': 'Camera configuration is valid; connection is checked on the NVIDIA computer at startup.'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
