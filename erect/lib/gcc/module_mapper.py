import asyncio

class ModuleRegistry:
    def __init__(self):
        self.modules = {}

    def _module_future(self, name):
        if not name in self.modules:
            self.modules[name] = asyncio.Future()

        return self.modules[name]

    async def module_required(self, name):
        await self._module_future(name)

    def module_provided(self, name):
        self._module_future(name).set_result(None)

    def module_exists(self, name):
        return name in self.modules and self.modules[name].done()

class Handler:
    def __init__(self, mapper, reader, writer):
        self.mapper = mapper
        self.reader = reader
        self.writer = writer
        self.task = None

    async def read(self):
        while line := await self.reader.readline():
            #print(f'< {line!r}', file=sys.stderr)
            yield tuple(line.decode('utf-8').strip().split())

    def write(self, line):
        line = line + '\n'
        self.writer.write(line.encode('utf-8'))
        #print(f'> {line!r}', file=sys.stderr)

    async def handle(self, command):
        match command:
            case ('HELLO', '1', compiler, ident):
                self.task = self.mapper.env._task_from_ident(ident)
                return 'HELLO 1 erect-modmap'

            case ('MODULE-REPO',):
                return f'PATHNAME {self.mapper.cmi_dir}'

            case ('MODULE-EXPORT', module, *_):
                return f'PATHNAME {self.mapper.gcm_name(module)}'

            case ('MODULE-IMPORT', module, *_):
                assert self.task is not None
                self.task._modules_required.append(module)
                async with self.task.mark_suspended():
                    await self.mapper.registry.module_required(module)
                return f'PATHNAME {self.mapper.gcm_name(module)}'

            case ('MODULE-COMPILED', module):
                self.mapper.registry.module_provided(module)
                if self.task:
                    self.task._modules_generated.append(module)
                return 'OK'

            case ('INCLUDE-TRANSLATE', path):
                return 'BOOL FALSE'

            case _:
                return 'ERROR'

    async def run(self):
        try:
            command_queue = []
            async for line in self.read():
                command_queue.append(line)
                if command_queue[-1][-1] == ';':
                    *command_queue[-1], _ = command_queue[-1]
                    continue

                while len(command_queue) > 1:
                    self.write(await self.handle(command_queue.pop(0)) + ' ;')
                self.write(await self.handle(command_queue.pop(0)))
                await self.writer.drain()
        finally:
            self.writer.close()

class ModuleMapper:
    def __init__(self, env, cmi_dir):
        self.env = env
        self.cmi_dir = cmi_dir
        self.registry = ModuleRegistry()
        self.port = None

    async def _handle_client(self, reader, writer):
        m = Handler(self, reader, writer)
        await m.run()

    async def start(self):
        server = await asyncio.start_server(self._handle_client, host = '::1', port = None)
        self.port = server.sockets[0].getsockname()[1]

    def gcc_arg(self, ident):
        assert self.port is not None
        return f'-fmodule-mapper=localhost:{self.port}?{ident}'

    def gcm_name(self, module):
        module = module.replace('/', ',')
        return f'{module}.gcm'

    def gcm_path(self, module):
        return self.cmi_dir / self.gcm_name(module)
