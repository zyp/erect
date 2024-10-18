import pathlib

from .context import Context, get_global_context

__all__ = ['Env']

class Env:
    ctx: Context
    build_dir: pathlib.Path

    def __init__(self, *, ctx = None, build_dir = None):
        self.ctx = ctx or get_global_context()
        self.build_dir = pathlib.Path(build_dir or 'build/')
