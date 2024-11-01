from importlib.metadata import version
from packaging.version import parse

class VersionError(Exception):
    pass

def require_version(required_version: str):
    required_version = parse(required_version)
    installed_version = parse(version('erect'))

    if required_version > installed_version:
        raise VersionError(f'Required erect version {required_version} is greater than installed version {installed_version}.')
