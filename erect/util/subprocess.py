import asyncio
import shlex

async def subprocess(cmd, *, stdout = None, stderr = None):
    print(shlex.join(str(e) for e in cmd))
    process = await asyncio.create_subprocess_exec(
        *(str(e) for e in cmd),
        stdout = stdout,
        stderr = stderr,
    )
    try:
        code = await process.wait()
        if code != 0:
            raise RuntimeError(f'Process returned {code}')
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()
