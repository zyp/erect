import importlib.util

def load_blueprint(filename):
    spec = importlib.util.spec_from_file_location('blueprint', filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
