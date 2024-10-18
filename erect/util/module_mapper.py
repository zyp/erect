import sys
import asyncio

class Handler:
    def __init__(self, cmi_dir, reader, writer):
        self.cmi_dir = cmi_dir
        self.reader = reader
        self.writer = writer

    async def read(self):
        while line := await self.reader.readline():
            #print(f'< {line!r}', file=sys.stderr)
            yield tuple(line.decode('utf-8').strip().split())

    def write(self, line):
        line = line + '\n'
        self.writer.write(line.encode('utf-8'))
        #print(f'> {line!r}', file=sys.stderr)

    def handle(self, command):
        match command:
            case ('HELLO', '1', *_):
                return 'HELLO 1 erect-modmap'

            case ('MODULE-REPO',):
                return f'PATHNAME {self.cmi_dir}'

            case ('MODULE-EXPORT', module, *_):
                return f'PATHNAME {module}.gcm'

            case ('MODULE-IMPORT', module, *_):
                return f'PATHNAME {module}.gcm'

            case ('MODULE-COMPILED', module):
                return 'OK'

            case ('INCLUDE-TRANSLATE', path):
                return 'BOOL FALSE'

            case _:
                return 'ERROR'

    async def run(self):
        command_queue = []
        async for line in self.read():
            command_queue.append(line)
            if command_queue[-1][-1] == ';':
                *command_queue[-1], _ = command_queue[-1]
                continue

            while len(command_queue) > 1:
                self.write(self.handle(command_queue.pop(0)) + ' ;')
            self.write(self.handle(command_queue.pop(0)))
            await self.writer.drain()
        self.writer.close()

async def start_tcp(cmi_dir):
    async def handle_client(reader, writer):
        m = Handler(cmi_dir, reader, writer)
        await m.run()

    return await asyncio.start_server(handle_client, host = '::1', port = None)

class ModuleMapper:
    def __init__(self, cmi_dir):
        self.port = None
        self.cmi_dir = cmi_dir

    async def start(self):
        server = await start_tcp(self.cmi_dir)
        self.port = server.sockets[0].getsockname()[1]

    @property
    def gcc_arg(self):
        assert self.port is not None
        return f'-fmodule-mapper=localhost:{self.port}'

async def connect_stdin_stdout():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout)
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    return reader, writer

async def async_main(cmi_dir):
    reader, writer = await connect_stdin_stdout()

    m = Handler(cmi_dir, reader, writer)
    await m.run()

def main():
    if len(sys.argv) > 1:
        cmi_dir = sys.argv[1]
    else:
        cmi_dir = 'build/cmi/'

    asyncio.run(async_main(cmi_dir))
