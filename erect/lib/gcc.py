import pathlib
import asyncio

from .. import core
from ..util.subprocess import subprocess
from ..util.module_mapper import ModuleMapper

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
            self.module_mapper = ModuleMapper(self.build_dir / 'cmi')
            self.ctx.start_async(self.module_mapper.start())
        else:
            self.module_mapper = None

    def executable(self, output_file, source_files, **kwargs):
        return Link(self, output_file, [pathlib.Path(f) for f in source_files], **kwargs)

class ScanDeps(core.Task):
    env: Env

    def __new__(cls, env: Env, source_file):
        try:
            self = super().__new__(cls, env.ctx, ('scan_deps', env.build_dir, source_file))
        except core.TaskExists as e:
            if e.task.env == env:
                return e.task
            raise

        self.env = env
        self.source_file = source_file
        self.object_file = self.env.build_dir / 'objects' / source_file.with_suffix('.o')
        self.dep_file = self.env.build_dir / 'objects' / source_file.with_suffix('.d')
        self.add_input_files(source_file)
        self.add_output_files(self.dep_file)
        return self

    def input_metadata(self):
        return super().input_metadata() | {
            'toolchain_prefix': self.env.toolchain_prefix,
            'toolchain_suffix': self.env.toolchain_suffix,
            'flags': self.env.cflags if self.source_file.suffix == '.c' else self.env.cxxflags,
            'defines': self.env.defines,
            'include_path': self.env.include_path,
        }

    async def run(self):
        source_file = self.source_file
        object_file = self.object_file
        dep_file = self.dep_file
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
                    self.env.module_mapper.gcc_arg,
                ])

        for define in self.env.defines:
            flags.extend(['-D', define])
        for path in self.env.include_path:
            flags.extend(['-I', path])

        await subprocess([
            compiler,
            *flags,
            '-MMD', '-E',
            source_file,
            '-MT', object_file,
            '-MF', dep_file,
        ], stdout = asyncio.subprocess.DEVNULL)

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
        module_deps = []
        module_gens = []

        for f in depmap[str(object_file)]:
            if f.endswith('.c++m'):
                f = self.env.build_dir / 'cmi' / f.replace('.c++m', '.gcm')

            file_deps.append(pathlib.Path(f))

        for dep in depmap[str(object_file)]:
            if dep.endswith('.c++m'):
                module_deps.append(dep[:-5])

        for dep in depmap.get('.PHONY', []):
            if dep.endswith('.c++m'):
                module_gens.append(dep[:-5])

        # Add included files as input files to trigger a rerun of this task if any changes in the future.
        self.add_input_files(*(f for f in file_deps if f.suffix != '.gcm'))

        return {
            'file_deps': file_deps,
            'module_deps': module_deps,
            'module_gens': module_gens,
        }

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
        self.scan_deps = ScanDeps(env, source_file)
        self.dependencies.append(self.scan_deps)
        #self.add_input_files(source_file) # This is added implicitly through scan_deps.
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

    def dynamic_deps(self):
        self.add_input_files(*self.scan_deps.result['file_deps'])

        return []

    async def run(self):
        source_file = self.source_file
        object_file = self.object_file
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
                    self.env.module_mapper.gcc_arg,
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
        ])

    async def post_run(self):
        # Report that modules are built.
        for m in self.scan_deps.result['module_gens']:
            self.add_output_files(self.env.build_dir / f'cmi/{m}.gcm')

class ModuleCheck(core.Task):
    env: Env

    def __new__(cls, env, target, source_files):
        self = super().__new__(cls, env.ctx, ('module_check', env.build_dir, target))
        self.env = env
        self.scan_deps_tasks = [ScanDeps(env, f) for f in source_files]
        self.dependencies.extend(self.scan_deps_tasks)
        return self

    async def run(self):
        generated_modules = set()

        for t in self.scan_deps_tasks:
            generated_modules.update(t.result['module_gens'])

        for t in self.scan_deps_tasks:
            for m in t.result['module_deps']:
                if m not in generated_modules:
                    raise Exception(f'Module {m} required by {t.source_file} does not exist.')

class Link(core.Task):
    env: Env

    def __new__(cls, env, target, source_files, ld_script = None):
        self = super().__new__(cls, env.ctx, ('link', env.build_dir, target))
        self.env = env
        self.target = target
        self.dependencies.append(ModuleCheck(env, target, source_files))
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
