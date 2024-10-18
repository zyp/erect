from .lib import gcc, jinja2

class Env(
    gcc.Env,
    jinja2.Env,
):
    pass
