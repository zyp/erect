import pathlib
import asyncio

from ... import core
from ...util.subprocess import subprocess
from .module_mapper import ModuleMapper

__all__ = ['Compile', 'Link']

class Env(core.Env):
    toolchain_prefix: str
    'GCC toolchain prefix'
    toolchain_suffix: str
    'GCC toolchain suffix'

    cflags: list[str]
    'C compiler flags'
    cxxflags: list[str]
    'C++ compiler flags'
    ldflags: list[str]
    'Linker flags'

    defines: list[str]
    'C/C++ preprocessor defines'
    include_path: list[str | pathlib.Path]
    'Include path'

    def __init__(self, *, cxx_modules = False, **kwargs):
        super().__init__(**kwargs)

        self.toolchain_prefix = ''
        self.toolchain_suffix = ''
        self.cflags = []
        self.cxxflags = []
        self.ldflags = []
        self.defines = []
        self.include_path = []

        if cxx_modules:
            self.module_mapper = ModuleMapper(self, self.build_dir / 'cmi')
            self.ctx.start_async(self.module_mapper.start())
        else:
            self.module_mapper = None

    def _task_from_ident(self, ident):
        if ident.endswith('.cpp'):
            return self.ctx.tasks.get(core.TaskID('compile', self.build_dir, ident))
        else:
            return self.ctx.tasks.get(core.TaskID('header_module', self.build_dir, ident))

    def executable(self, output_file, source_files, **kwargs):
        return Link(self, output_file, [pathlib.Path(f) for f in source_files], **kwargs)

    def header_module(self, header):
        return HeaderModule(self, header)

class Compile(core.Task):
    env: Env

    def __new__(cls, env, source_file):
        try:
            self = super().__new__(cls, env.ctx, ('compile', env.build_dir, source_file))
        except core.TaskExists as e:
            if e.task.env == env:
                return e.task
            raise

        self.env = env
        self.source_file = source_file
        self.object_file = self.env.build_dir / 'objects' / source_file.with_suffix('.o')
        self._modules_required = []
        self._modules_generated = []
        self.add_input_files(source_file)
        self.add_output_files(self.object_file)
        return self

    def input_metadata(self):
        return super().input_metadata() | {
            'toolchain_prefix': self.env.toolchain_prefix,
            'toolchain_suffix': self.env.toolchain_suffix,
            'flags': self.env.cflags if self.source_file.suffix == '.c' else self.env.cxxflags,
            'defines': self.env.defines,
            'include_path': self.env.include_path,
        }

    async def pre_run(self):
        # Do an early up-to-date check.
        if self._uptodate():
            cache = self.ctx.cache[self.id.mangled]

            # If the early check indicates we're up to date, ensure all required modules are (re-)built before we proceed to the actual check.
            for module in cache['result']['modules_required']:
                await self.env.module_mapper.registry.module_required(module)

    async def run(self):
        source_file = self.source_file
        object_file = self.object_file
        dep_file = object_file.with_suffix('.d')
        cmi_dir = self.env.build_dir / 'cmi'

        # Ensure output directory exists.
        object_file.parent.mkdir(parents = True, exist_ok = True)

        if source_file.suffix == '.c':
            compiler = f'{self.env.toolchain_prefix}gcc{self.env.toolchain_suffix}'
            flags = self.env.cflags.copy()

        else:
            compiler = f'{self.env.toolchain_prefix}g++{self.env.toolchain_suffix}'
            flags = self.env.cxxflags.copy()
            if self.env.module_mapper is not None:
                flags.extend([
                    '-fmodules-ts',
                    self.env.module_mapper.gcc_arg(source_file),
                ])

        for define in self.env.defines:
            flags.extend(['-D', define])
        for path in self.env.include_path:
            flags.extend(['-I', path])

        await subprocess([
            compiler,
            *flags,
            '-c',
            source_file,
            '-o', object_file,
            '-MMD',
            '-MF', dep_file,
        ])

        depmap = {}

        with open(dep_file) as f:
            contents = f.read().replace('\\\n', ' ')
            for line in contents.split('\n'):
                if line.count(':') != 1:
                    continue
                targets, deps = line.split(':')
                targets = targets.split()
                deps = deps.replace('|', '').split()

                for t in targets:
                    if t not in depmap:
                        depmap[t] = []
                    depmap[t].extend(deps)

        file_deps = []

        for f in depmap[str(object_file)]:
            if f.endswith('.c++m'):
                continue

            file_deps.append(pathlib.Path(f))

        # Add included files as input files to trigger a rerun of this task if any changes in the future.
        self.add_input_files(*(f for f in file_deps if f != source_file))

        # Add generated CMI files as output files.
        self.add_output_files(*(self.env.module_mapper.gcm_path(module) for module in self._modules_generated))

        return {
            'modules_required': self._modules_required,
            'modules_generated': self._modules_generated,
        }

    async def post_run(self):
        # Report that modules are built.
        registry = self.env.module_mapper.registry
        for m in self.result['modules_generated']:
            if not registry.module_exists(m):
                registry.module_provided(m)

class HeaderModule(core.Task):
    env: Env

    def __new__(cls, env, header):
        try:
            self = super().__new__(cls, env.ctx, ('header_module', env.build_dir, header))
        except core.TaskExists as e:
            if e.task.env == env:
                return e.task
            raise

        self.env = env
        self.header = header
        self._modules_generated = []
        return self

    def input_metadata(self):
        return super().input_metadata() | {
            'toolchain_prefix': self.env.toolchain_prefix,
            'toolchain_suffix': self.env.toolchain_suffix,
            'flags': self.env.cxxflags,
            'defines': self.env.defines,
            'include_path': self.env.include_path,
        }

    async def run(self):
        cmi_dir = self.env.build_dir / 'cmi'

        assert self.env.module_mapper is not None

        compiler = f'{self.env.toolchain_prefix}g++{self.env.toolchain_suffix}'
        flags = self.env.cxxflags.copy()
        flags.extend([
            '-fmodules-ts',
            self.env.module_mapper.gcc_arg(self.header),
        ])

        for define in self.env.defines:
            flags.extend(['-D', define])
        for path in self.env.include_path:
            flags.extend(['-I', path])

        await subprocess([
            compiler,
            *flags,
            '-x', 'c++-user-header',
            '-c',
            self.header,
        ])

        # Add generated CMI files as output files.
        self.add_output_files(*(self.env.module_mapper.gcm_path(module) for module in self._modules_generated))

        return {
            'modules_generated': self._modules_generated,
        }

    async def post_run(self):
        # Report that modules are built.
        registry = self.env.module_mapper.registry
        for m in self.result['modules_generated']:
            if not registry.module_exists(m):
                registry.module_provided(m)

class Link(core.Task):
    env: Env

    def __new__(cls, env, target, source_files, ld_script = None):
        self = super().__new__(cls, env.ctx, ('link', env.build_dir, target))
        self.env = env
        self.target = target
        self.source_files = source_files,
        self.object_tasks = [Compile(env, f) for f in source_files]
        self.ld_script = ld_script
        #self.dependencies.extend(self.object_tasks) # This is added implicitly through input_files
        self.elf_file = self.env.build_dir / self.target
        self.add_input_files(*(t.object_file for t in self.object_tasks))
        self.add_output_files(self.elf_file)
        if self.ld_script is not None:
            self.add_input_files(self.ld_script)
        return self

    def input_metadata(self):
        return super().input_metadata() | {
            'toolchain_prefix': self.env.toolchain_prefix,
            'toolchain_suffix': self.env.toolchain_suffix,
            'source_files': self.source_files,
            'ld_script': self.ld_script,
            'toolchain': self.env.toolchain_prefix,
            'flags': self.env.ldflags,
        }

    async def run(self):
        object_files_str = ' '.join(str(t.object_file) for t in self.object_tasks)
        elf_file = self.elf_file

        # Ensure output directory exists.
        elf_file.parent.mkdir(parents = True, exist_ok = True)

        ldflags = self.env.ldflags[:]

        if self.ld_script is not None:
            ldflags.extend(['-T', self.ld_script])

        await subprocess([
            f'{self.env.toolchain_prefix}g++{self.env.toolchain_suffix}',
            *ldflags,
            *(str(t.object_file) for t in self.object_tasks),
            '-o', elf_file,
        ])

        return elf_file
