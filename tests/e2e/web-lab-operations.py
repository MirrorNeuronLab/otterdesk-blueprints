"""Opt-in browser gate: real PLR trackers, assets, sockets and Job UI proxy; no model.

Run with the blueprint test environment and pinned PLR dependencies installed.
WEB_LAB_VISUALIZER_VENDOR selects the build-time vendor folder (assets.json + files).
"""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
import conftest  # noqa: E402,F401 - installs declared sibling source paths
sys.path.insert(0, str(conftest.WORKSPACE / 'mn-api'))
sys.path.insert(0, str(ROOT / 'web_lab_operator/payloads'))
from domain.lab import SimulatedLab  # noqa: E402
from domain.visualizer import LabVisualizer  # noqa: E402
from mn_api.web_ui_server import create_app  # noqa: E402
import uvicorn  # noqa: E402


async def main():
    output = Path(os.environ.get('WEB_LAB_E2E_OUTPUT', '/private/tmp/web-lab-live-operations'))
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads((ROOT / 'tests/fixtures/web_lab_operator/expected_plan.json').read_text())
    lab = SimulatedLab(plan)
    await lab.setup()
    projection = {'status':'running', 'summary':'Synthetic live operation acceptance',
                  'reason':'Tracker observations only.', 'current_step':'transfer_water',
                  'steps_completed':0, 'steps_total':2, 'events':[], 'state':lab.observe(), 'operation':None}
    viewer = LabVisualizer(lab.lh, lambda: projection,
                           vendor_root=Path(os.environ['WEB_LAB_VISUALIZER_VENDOR']))
    port = await viewer.start('127.0.0.1', 0)
    handle = {'url':f'http://127.0.0.1:{port}/', 'status':'running',
              'metadata':{'proxy':{'http_ports':[port], 'websocket_ports':[port]},
                          'readiness':{'ready':True}}}

    class HandleApi(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?')[0] != '/api/v1/jobs/lab-ui-check/ui':
                self.send_error(404)
                return
            content = json.dumps({'web_ui':handle}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *_args):
            pass

    process = None
    with contextlib.ExitStack() as cleanup:
        api = ThreadingHTTPServer(('127.0.0.1',0), HandleApi)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        cleanup.callback(api.server_close)
        cleanup.callback(api.shutdown)
        listener = socket.socket()
        listener.bind(('127.0.0.1',0))
        proxy_port = listener.getsockname()[1]
        proxy = uvicorn.Server(uvicorn.Config(
            create_app(api_url=f'http://127.0.0.1:{api.server_port}/api/v1'),
            log_level='error', ws='websockets-sansio'))
        thread = threading.Thread(target=proxy.run, kwargs={'sockets':[listener]}, daemon=True)
        thread.start()
        cleanup.callback(thread.join, 5)
        cleanup.callback(setattr, proxy, 'should_exit', True)
        try:
            process = await asyncio.create_subprocess_exec(
                'node', str(Path(__file__).with_suffix('.cjs')),
                f'http://127.0.0.1:{proxy_port}/job-ui-proxy/lab-ui-check/{port}/', str(output),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

            async def receipt(expected):
                actual = (await asyncio.wait_for(process.stdout.readline(), timeout=30)).decode().strip()
                if actual != expected:
                    raise AssertionError(f'Expected browser {expected!r}, got {actual!r}')

            await receipt('ready')

            async def tick(operation):
                projection.update(operation=operation, state=lab.observe())
                await viewer.publish()
                wells = {lab.well(name).name: state['volume_ul'] for name,state in lab.observe()['wells'].items()
                         if name in {'source/A2','destination/A1'}}
                process.stdin.write((json.dumps({'operation':operation,'wells':wells,
                                                'steps_completed':projection['steps_completed']})+'\n').encode())
                await process.stdin.drain()
                await receipt('observed')

            transfer = {**plan['steps'][0], 'source':'source/A2'}
            await lab.perform(transfer, lambda:None, tick)
            projection['steps_completed'] = 1
            projection['current_step'] = 'mix_water'
            await lab.perform(plan['steps'][1], lambda:None, tick)
            projection.update(status='completed', steps_completed=2, operation=None)
            await viewer.publish()
            process.stdin.write(b'{"done":true}\n')
            await process.stdin.drain()
            await receipt('terminal')
            await viewer.close()
            process.stdin.write(b'{"closed":true}\n')
            await process.stdin.drain()
            await receipt('verified')
            assert await asyncio.wait_for(process.wait(), timeout=10) == 0
            print('Verified live transfer, separate mix half-cycles, deck highlights, reconnect, resize and terminal cleanup through the Job UI proxy.')
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            await viewer.close()
            await lab.stop()


if __name__ == '__main__':
    asyncio.run(main())
