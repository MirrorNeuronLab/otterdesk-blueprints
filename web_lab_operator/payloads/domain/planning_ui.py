"""An empty native deck while the bounded intake or model phase is working."""

import asyncio
from concurrent.futures import Future
from threading import Thread

from .live_ui import LiveLabUi


class PlanningUi:
    def __init__(self, block, phase):
        self.block = block
        self.phase = phase
        self.ready = Future()
        self.finished = Future()
        self.stop_reason = Future()
        self.thread = Thread(target=self._run, name='web-lab-planning-ui', daemon=True)

    def start(self):
        self.thread.start()
        # Listener startup and the SDK's bounded readiness/claim checks must
        # finish before model dispatch. They run on their own serving loop.
        self.ready.result(timeout=15)

    def stop(self, status):
        if self.thread.ident is None:
            return
        self.stop_reason.set_result(status)
        try:
            self.finished.result(timeout=10)
        finally:
            self.thread.join(timeout=1)

    def _run(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            if self.ready.done():
                self.finished.set_exception(error)
            else:
                self.ready.set_exception(error)
                self.finished.set_result(None)
        else:
            self.finished.set_result(None)

    async def _serve(self):
        from pylabrobot.resources.hamilton import STARLetDeck

        projection = {
            'status': self.phase,
            'summary': 'Preparing the lab procedure.' if self.phase == 'preparing' else 'Planning the simulated procedure.',
            'reason': 'The deck will populate after the procedure is validated.',
            'state': {'wells': {}, 'tips_remaining': None},
            'current_step': '', 'steps_completed': 0, 'events': [],
        }
        ui = LiveLabUi(self.block, STARLetDeck(), lambda: projection)
        status = 'failed'
        try:
            await ui.start()
            self.ready.set_result(True)
            status = await asyncio.wrap_future(self.stop_reason)
        finally:
            await ui.close(status)


def _start(block, phase):
    view = PlanningUi(block, phase)
    block.resources['web_lab_planning_ui'] = view
    view.start()


def prepare(block, _inputs):
    _start(block, 'preparing')


def plan(block, _inputs):
    _start(block, 'planning')


def stop(block, outcome):
    view = block.resources.pop('web_lab_planning_ui', None)
    if view is not None:
        view.stop('stopped' if outcome['status'] == 'completed' else outcome['status'])
