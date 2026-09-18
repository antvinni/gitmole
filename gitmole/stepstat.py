"""`python -m gitmole.stepstat STATS -- ARGV...`: run one pipeline step, then write its wall time and peak
memory (the largest process in its tree, from RUSAGE_CHILDREN) to STATS, and exit with its code. The run
records them per step in meta.json; the --json export keeps them in its envelope, since they vary."""
import json
import resource
import subprocess
import sys
import time


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    stats, command = args[0], args[args.index("--") + 1:]
    start = time.monotonic()
    rc = subprocess.call(command)
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    with open(stats, "w") as fh:
        json.dump({"seconds": round(time.monotonic() - start, 2),
                   "peak_mb": round(peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024, 1)}, fh)
    return rc


if __name__ == "__main__":
    sys.exit(main())
