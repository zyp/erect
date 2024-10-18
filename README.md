# Erect

1. (*verb*, *transitive*) To put up by the fitting together of materials or parts.

## Introduction

Erect is a build system aimed at building speciality (e.g. embedded) software.

Design goals include:
- Support for C++20 modules.
- Type annotations and docstrings to help editors help you write blueprints.
- Embeddability (create tasks and run the dependency engine from within another python application).

## Status and roadmap

- Basic functionality is in place.
- The API is not considered stable yet.
- Error handling and path handling needs to be improved.
- Documentation and tests are not written yet.

## Usage

Erect will look for a file named `blueprint.py`, whose contents might look like so:

```python
from erect import Env

env = Env()

env.executable('hello', ['main.cpp'])
```

When you run `erect`, this file will be loaded, which creates a build environment and the tasks necessary to build an executable from `main.cpp`.
All build artifacts will go into the environment's build directory which defaults to `build/`, so the resulting executable will be `build/hello`.
After the blueprint is done, Erect will execute the created tasks in dependency order.
