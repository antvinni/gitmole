"""`python launch.py MODULE ARGS...`: run gitmole.MODULE as `python -m` would, with THIS gitmole first on the
import path. Pipeline steps run with the analysed repository as their working directory, and `python -m`
puts the working directory first: a repository with its own gitmole/ package (gitmole's own history, a
fork) would otherwise run its copy of the step. Invoked by path, so the working directory is never searched."""
import os
import runpy
import sys

if __name__ == "__main__":
    here = os.path.dirname(os.path.realpath(__file__))
    sys.path[0] = os.path.dirname(here)   # the package's parent, in place of this script's own directory
    module = sys.argv[1]
    sys.argv = [module] + sys.argv[2:]
    runpy.run_module(module, run_name="__main__", alter_sys=True)
