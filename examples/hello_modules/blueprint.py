from erect import Env

env = Env(cxx_modules = True)

env.executable('hello', ['main.cpp', 'foo.cpp'])
