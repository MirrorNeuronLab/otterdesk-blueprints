"""One phase-owned PyLabRobot page, published through the runtime UI contract."""

import asyncio
import json
from uuid import uuid4

from mn_sdk_web_ui import claim_web_ui, mark_web_ui_status, resolve_web_ui_binding

from .visualizer import LabVisualizer


class LiveLabUi:
    def __init__(self, block, resource, projection):
        self.block = block
        self.visualizer = LabVisualizer(resource, projection)
        self.generation = uuid4().hex
        self.claimed = False

    async def start(self):
        block = self.block
        binding = resolve_web_ui_binding(block.config, environment=block.environment)
        port = await self.visualizer.start(binding.host, binding.port)
        url = binding.advertised_url(port, environment=block.environment)
        self.claimed = True
        await asyncio.to_thread(claim_web_ui, block.job_directory, job_id=block.job_id,
                               url=url, title='Web lab', service_name='web-lab',
                               node_id=block.agent_id or 'lab_simulator', generation=self.generation,
                               http_ports=[port], websocket_ports=[port], status='running',
                               metadata={'simulation_only': True})
        metadata = json.loads((block.job_directory / 'web_ui.json').read_text()).get('metadata', {})
        if metadata.get('generation') != self.generation or not metadata.get('readiness', {}).get('ready'):
            raise RuntimeError("The web lab page or its required assets are unavailable.")

    async def close(self, status='stopped'):
        try:
            await self.visualizer.close()
        finally:
            if self.claimed and (self.block.job_directory / 'web_ui.json').is_file():
                await asyncio.to_thread(mark_web_ui_status, self.block.job_directory,
                                       job_id=self.block.job_id, status=status,
                                       expected_generation=self.generation)

    async def publish(self):
        await self.visualizer.publish()
