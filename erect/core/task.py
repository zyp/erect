import asyncio
import time
import pathlib
import contextlib

from .context import Context
from .file import File

__all__ = ['TaskExists', 'TaskID', 'Task']

class TaskExists(Exception):
    def __init__(self, id, task):
        super().__init__(f'Task with id {id} already exists')
        self.id = id
        self.task = task

class TaskID(tuple):
    def __new__(cls, *args):
        assert args

        if len(args) == 1 and isinstance(args[0], tuple):
            args, = args

        for i, e in enumerate(args):
            for type in [str, pathlib.Path, int]:
                if isinstance(e, type):
                    break
            else:
                raise TypeError(f'TaskID element {i} is unsupported: {e}')
        
        return super().__new__(cls, (str(e) for e in args))

    @property
    def mangled(self):
        return ';'.join(self)

    @property
    def str(self):
        return ' '.join(self)

class Task:
    ctx: Context
    id: TaskID

    def __new__(cls, ctx, id):
        id = TaskID(id)
        if id in ctx.tasks:
            raise TaskExists(id, ctx.tasks[id])
        ctx.tasks[id] = self = super().__new__(cls)
        self.ctx = ctx
        self.id = id
        self.dependencies = []
        self.lock = asyncio.Lock()
        self.done = False
        self.result = None

        self._input_files = []
        self._output_files = []
        self._events = []
        return self

    def add_input_files(self, *files):
        files = [File(self.ctx, path) for path in files]
        self._input_files.extend(files)

    def add_output_files(self, *files):
        files = [File(self.ctx, path) for path in files]
        self._output_files.extend(files)
        for file in files:
            assert file.generator_task is None
            file.generator_task = self

    def input_metadata(self):
        return {}

    def dynamic_deps(self):
        return []

    async def pre_run(self):
        pass

    async def run(self):
        raise NotImplementedError()

    async def post_run(self):
        pass

    def _uptodate(self):
        # Uncached tasks are not up to date.
        if not self.id.mangled in self.ctx.cache:
            return False
        cache = self.ctx.cache[self.id.mangled]

        # Check if input metadata changed.
        if cache.get('input_metadata') != self.input_metadata():
            return False

        # Check if any files doesn't match their fingerprints.
        for path, fingerprint in cache.get('file_fingerprints', {}).items():
            if not fingerprint.check(path):
                return False

        ## TODO: This condition should be updated.
        #if not self._input_files or not self._output_files:
        #    return False
        
        for f in self._input_files:
            assert f.path.exists(), f'Required file {f.path} for task {self.id} does not exist.'
        
        for f in self._output_files:
            if not f.path.exists():
                return False
        
        #if max(f.path.stat().st_mtime for f in self._input_files) > min(f.path.stat().st_mtime for f in self._output_files):
        #    return False

        return True

    def _save_cache(self):
        self.ctx.cache[self.id.mangled] = {
            'input_metadata': self.input_metadata(),
            'file_fingerprints': {f.path: f.get_fingerprint() for f in [*self._input_files, *self._output_files]},
            'result': self.result,
        }

    async def _run(self):
        async with self.lock:
            if self.done:
                return self.result

            await async_run(self.dependencies + self._input_files)

            await async_run(self.dynamic_deps())

            await async_run(self._input_files)

            await self.pre_run()

            async with self.ctx.task_semaphore:
                self._events.append((time.monotonic(), 'running'))
                if self._uptodate():
                    self.result = self.ctx.cache[self.id.mangled]['result']
                else:
                    self.result = await self.run()
                    self._save_cache()
                await self.post_run()
                self._events.append((time.monotonic(), 'done'))

            self.done = True

    @contextlib.asynccontextmanager
    async def mark_suspended(self):
        self._events.append((time.monotonic(), 'suspended'))
        self.ctx.task_semaphore.release()
        try:
            yield
        finally:
            await self.ctx.task_semaphore.acquire()
            self._events.append((time.monotonic(), 'running'))

async def async_run(tasks):
    async with asyncio.TaskGroup() as tg:
        for task in tasks:
            tg.create_task(task._run())
