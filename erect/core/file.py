import pathlib
import asyncio
import hashlib
from dataclasses import dataclass

__all__ = ['Fingerprint', 'File']

# TODO: memoize?
def _hash_file(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').digest()

@dataclass
class Fingerprint:
    mtime_ns: int
    hash: bytes

    @classmethod
    def create(cls, path):
        assert path.exists()

        return cls(
            mtime_ns = path.stat().st_mtime_ns,
            hash = _hash_file(path),
        )

    def check(self, path):
        # Files that doesn't exist matches nothing.
        if not path.exists():
            return False
        
        # Assume file is unchanged if mtime matches.
        if path.stat().st_mtime_ns == self.mtime_ns:
            return True

        # Check if hash is matching.
        return _hash_file(path) == self.hash

class File:
    path: pathlib.Path

    def __new__(cls, ctx, path):
        path = pathlib.Path(path)
        if path in ctx.files:
            return ctx.files[path]
        ctx.files[path] = self = super().__new__(cls)
        self.ctx = ctx
        self.path = path

        self._generator_task = None
        return self

    @property
    def generator_task(self):
        return self._generator_task

    @generator_task.setter
    def generator_task(self, task):
        assert self._generator_task is None
        self._generator_task = task

    async def _run(self):
        if self.generator_task is not None:
            await self.generator_task._run()

        assert self.path.exists()

    def get_fingerprint(self):
        return Fingerprint.create(self.path)
