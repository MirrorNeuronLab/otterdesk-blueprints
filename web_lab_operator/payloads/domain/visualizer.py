"""Serve the pinned PyLabRobot visualizer and the lab monitor on one UI binding.

The native Visualizer owns resource events and the browser protocol. This bridge
replaces its two threaded listeners with one async listener so all assets and
WebSocket traffic stay inside the existing runtime's authenticated UI proxy.
"""

import asyncio
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from pylabrobot.visualizer.visualizer import Visualizer
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response
from websockets.exceptions import ConnectionClosed

ASSETS = Path(__file__).resolve().parents[1] / 'web_assets'
VENDOR = Path('/opt/web-lab/visualizer-vendor')
WS_CONSTRUCTOR = 'new WebSocket(`ws://${wsHost}:${wsPort}/`)'
# The Job proxy has a separate /ws/<upstream path> route at the port root.
# Both forms stay on the page's origin, including when the Job runs remotely.
LOCAL_CONSTRUCTOR = ('new WebSocket(new URL(window.__MN_JOB_UI_PROXY_BASE__ ? '
                     '"../ws/visualizer/ws" : "ws", window.location.href).href.replace(/^http/, "ws"))')


def visualizer_asset(path, native_root, vendor_root=VENDOR):
    if path == 'favicon.png':
        return (vendor_root / 'img/logo.png').read_bytes(), 'image/png'
    if path == 'index.html':
        content = (native_root / 'index.html').read_text()
        manifest = json.loads((vendor_root / 'assets.json').read_text())
        for url, item in manifest.items():
            content = content.replace(url, 'vendor/' + item['file'])
        if 'https://' in content or 'http://' in content:
            raise ValueError("The pinned visualizer contains an undeclared external asset.")
        content = content.replace('/favicon.png', 'favicon.png')
        content = content.replace('</head>', '<link rel="stylesheet" href="workspace.css"></head>')
        content = content.replace('</body>', '<script src="workspace.js"></script></body>')
        for key, value in {'ws_port': '0', 'fs_port': '0', 'source_filename': 'Web Lab Operator', 'liquid_color': '4F9B89'}.items():
            content = content.replace('{{ ' + key + ' }}', value)
        return content.encode(), 'text/html; charset=utf-8'
    if path in {'workspace.css', 'workspace.js'}:
        source = ASSETS / path
    elif path.startswith(('vendor/', 'img/')):
        # Build-time assets are a closed inventory, including the icon fonts.
        files = {item['file'] for item in json.loads((vendor_root / 'assets.json').read_text()).values()}
        relative = path.removeprefix('vendor/')
        if relative not in files:
            raise FileNotFoundError(path)
        source = vendor_root / relative
    else:
        if path not in {'lib.js', 'vis.js', 'main.css', 'gif.js', 'gif.worker.js'}:
            raise FileNotFoundError(path)
        source = native_root / path
    content = source.read_bytes()
    if path == 'vis.js':
        text = content.decode()
        if text.count(WS_CONSTRUCTOR) != 1:
            raise ValueError("The installed PyLabRobot visualizer differs from the pinned interface.")
        content = text.replace(WS_CONSTRUCTOR, LOCAL_CONSTRUCTOR).encode()
    return content, mimetypes.guess_type(source.name)[0] or 'application/octet-stream'


class LabVisualizer(Visualizer):
    def __init__(self, resource, projection, *, vendor_root=VENDOR):
        super().__init__(resource=resource, open_browser=False, name='Web Lab Operator',
                         show_machine_tools_at_start=False)
        import pylabrobot.visualizer.visualizer as native
        self.native_root = Path(native.__file__).parent
        self.vendor_root = vendor_root
        self.projection = projection
        self.server = None

    async def start(self, host, port):
        self._loop = asyncio.get_running_loop()
        self.server = await serve(self._socket_handler, host, port,
                                  process_request=self.http, max_size=8192,
                                  ping_interval=20, close_timeout=2)
        self.setup_finished = True
        return self.server.sockets[0].getsockname()[1]

    async def _socket_handler(self, connection):
        try:
            await super()._socket_handler(connection)
        finally:
            if self._websocket is connection:
                self._websocket = None

    async def send_command(self, event, data=None, wait_for_response=True):
        connection = self._websocket
        try:
            return await super().send_command(event, data, wait_for_response)
        except ConnectionClosed:
            if self._websocket is connection:
                self._websocket = None
            if wait_for_response:
                raise
            # State notifications have no effect or acknowledgment authority.
            # A new viewer receives the complete current deck on its handshake.
            return None

    async def http(self, connection, request):
        path = urlsplit(request.path).path
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return None if path == '/visualizer/ws' else Response(403, 'Forbidden', Headers(), b'')
        try:
            if path == '/state':
                content, mime = json.dumps(self.projection(), allow_nan=False).encode(), 'application/json'
            elif path.startswith('/visualizer/'):
                content, mime = visualizer_asset(path.removeprefix('/visualizer/'), self.native_root, self.vendor_root)
            elif path in {'/', '/app.js', '/style.css'}:
                source = ASSETS / ('index.html' if path == '/' else path[1:])
                content, mime = source.read_bytes(), mimetypes.guess_type(source.name)[0] or 'text/plain'
            else:
                raise FileNotFoundError(path)
        except FileNotFoundError:
            return Response(404, 'Not found', Headers(), b'Not found')
        headers = Headers({'Content-Type': mime, 'Content-Length': str(len(content)),
                           'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                           'Referrer-Policy': 'no-referrer'})
        return Response(200, 'OK', headers, content)

    async def close(self):
        self._websocket = None
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        self.setup_finished = False
        self._websocket = None
