import pathlib
import asyncio
import time
import click

from .core import Context
from .util.load import load_blueprint
from .diagnostic.timeline import plot_timeline
from .diagnostic.graph import render_graph

@click.command()
@click.argument('targets', nargs = -1, type = click.Path(readable = False, path_type = pathlib.Path))
@click.option('-j', '--jobs', default = 1, help = 'Max parallel jobs.')
@click.option('--timeline', is_flag = True, help = 'Create a timeline plot after the build.')
@click.option('--graph', is_flag = True, help = 'Create a render of the dependency graph after the build.')
@click.option('--no-cache', is_flag = True, help = 'Don\'t use a cache file.')
def main(targets = None, jobs = None, timeline = False, graph = False, no_cache = False):
    main_start = time.monotonic()

    blueprint = pathlib.Path('blueprint.py')
    assert blueprint.exists()

    with Context(
        max_concurrent_tasks = jobs,
        cache_file = False if no_cache else None,
    ) as ctx:
        load_blueprint(blueprint)

        run_start = time.monotonic()

        tasks = []
        if targets:
            for target in targets:
                target_files = [file for file in ctx.files.values() if file.path.is_relative_to(target)]
                assert target_files, f'No targets matching {target}'
                tasks.extend(target_files)
        
        else:
            tasks = ctx.tasks.values()

        asyncio.run(ctx.run(tasks))

        if timeline:
            plot_timeline(ctx, main_start, run_start)

        if graph:
            render_graph(ctx)
