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
from domain.protocol import action_for, candidates, goal_results, initial_state  # noqa: E402
from domain.supervision import event_rows, risks_for  # noqa: E402
from domain.presentation import render  # noqa: E402
from mn_api.web_ui_server import create_app  # noqa: E402
import uvicorn  # noqa: E402


async def main():
    output = Path(os.environ.get('WEB_LAB_E2E_OUTPUT', '/private/tmp/web-lab-live-operations'))
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads((ROOT / 'tests/fixtures/web_lab_operator/expected_sample_plan.json').read_text())
    lab = SimulatedLab(plan)
    await lab.setup()
    projection = {'status':'running', 'summary':'Synthetic live operation acceptance',
                  'reason':'', 'current_step':'',
                  'steps_completed':0, 'steps_total':len(plan['steps']), 'events':[], 'state':lab.observe(), 'operation':None}
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
                         if name in {step.get('source'), step.get('destination'), step.get('well'),
                                     *step.get('alternate_sources', [])}}
                process.stdin.write((json.dumps({'operation':operation,'wells':wells,
                                                'steps_completed':projection['steps_completed'],
                                                'steps_total':len(plan['steps'])})+'\n').encode())
                await process.stdin.drain()
                await receipt('observed')

            trace = []
            for step in plan['steps']:
                before = lab.observe()
                risks = risks_for(step, before)
                projection.update(current_step=step['id'], operation=None, events=event_rows(trace) + [
                    {'step':step['id'], 'decision':'warning', 'reason':risk['message']} for risk in risks])
                await viewer.publish()
                if risks:
                    process.stdin.write((json.dumps({'risks':risks})+'\n').encode())
                    await process.stdin.drain()
                    await receipt('warned')
                source = candidates(step, before)[0] if step['kind'] == 'transfer' else ''
                decision = {'step_id':step['id'], 'source':source, 'reason':'Synthetic model choice for browser acceptance.',
                            'decision':'adapt' if source and source != step['source'] else 'execute'}
                action = action_for(step, before, decision)
                outcome = await lab.perform(action, lambda:None, tick)
                assert outcome['passed']
                trace.append({'step':step, 'action':action, 'decision':decision, 'before':before,
                              'after':lab.observe(), 'outcome':outcome, 'error':'', 'risks':risks})
                projection.update(steps_completed=len(trace), state=lab.observe(), events=event_rows(trace))
            assert all(goal['met'] for goal in goal_results(plan, lab.observe()))
            final = {'status':'completed', 'steps_total':len(plan['steps']), 'summary':plan['summary'],
                     'reason':'All simulated steps and final volume goals passed.'}
            (output / 'replay.html').write_text(render(final, {'initial':initial_state(plan), 'events':trace}))
            (output / 'empty.html').write_text(render({'status':'needs_review', 'steps_total':0,
                'reason':'Clarify the procedure before starting.'},
                {'initial':{'wells':{}, 'tips_remaining':None}, 'events':[]}))
            projection.update(**final, operation=None)
            await viewer.publish()
            process.stdin.write(b'{"done":true}\n')
            await process.stdin.drain()
            await receipt('terminal')
            await viewer.close()
            process.stdin.write(b'{"closed":true}\n')
            await process.stdin.drain()
            await receipt('verified')
            assert await asyncio.wait_for(process.wait(), timeout=10) == 0
            print('Verified all 20 sample steps, two shortage warnings, live volumes, mix half-cycles, replay, resizing, reconnect and terminal cleanup through the Job UI proxy.')
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            await viewer.close()
            await lab.stop()


if __name__ == '__main__':
    asyncio.run(main())
