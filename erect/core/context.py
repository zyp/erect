import asyncio
import shelve
import sys

__all__ = ['Context']

_global_context = None

class Context:
    def __init__(self, *,
        max_concurrent_tasks = None,
        cache_file = None,
    ):
        self.tasks = {}
        self.files = {}
        self._start_coros = []

        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_semaphore = asyncio.Semaphore(max_concurrent_tasks or 1)

        if cache_file is False:
            self.cache = {}
        else:
            self.cache = shelve.open(cache_file or '.erect')

    def __enter__(self):
        global _global_context
        assert _global_context is None, 'Global context already exists.'

        _global_context = self
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        global _global_context
        assert _global_context is self, 'Global context is not self.'

        _global_context = None

    async def _check_deadlock(self, tg):
        loop = asyncio.get_running_loop()

        while True:
            await asyncio.sleep(0.1)

            if self.task_semaphore._value >= self.max_concurrent_tasks and not loop._ready:
                tg._abort()
                print('All remaining tasks are blocked, aborting.', file = sys.stderr)
                return

    def start_async(self, coro):
        self._start_coros.append(coro)

    async def run(self, tasks):
        for coro in self._start_coros:
            await coro

        async with asyncio.TaskGroup() as tg:
            asyncio.create_task(self._check_deadlock(tg))

            for task in tasks:
                tg.create_task(task._run())

def get_global_context():
    assert _global_context is not None, 'Global context is not set.'

    return _global_context
