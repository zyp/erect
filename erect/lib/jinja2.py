from ..core.task import Task
from ..core.env import Env

import pathlib
import jinja2

__all__ = ['Jinja2']

class Env(Env):
    pass

loader = jinja2.FileSystemLoader('.')

jinja2_env = jinja2.Environment(
    loader = loader,
    trim_blocks = True,
    lstrip_blocks = True,
)

jinja2_env.filters['hex'] = lambda value: '%#x' % value
jinja2_env.filters['size_prefix'] = lambda value: '%d%s' % next((value / 1024**i, c) for i, c in [(2, 'M'), (1, 'k'), (0, '')] if value % 1024**i == 0)

class Jinja2(Task):
    def __new__(cls, env, target, source, **kwargs):
        self = super().__new__(cls, env.ctx, ('jinja2', env.build_dir, target))
        self.env = env
        self.source = pathlib.Path(source)
        self.target = env.build_dir / 'generated' / target
        self.data = kwargs
        self.add_input_files(self.source)
        self.add_output_files(self.target)
        return self

    def input_metadata(self):
        return super().input_metadata() | {
            'source': self.source,
            'data': self.data,
        }

    async def run(self):
        print(self.id.str)

        template = jinja2_env.get_template(str(self.source))
        output = template.render(**self.data) + '\n'


        # Ensure output directory exists.
        self.target.parent.mkdir(parents = True, exist_ok = True)

        with open(self.target, 'w') as f:
            f.write(output)
