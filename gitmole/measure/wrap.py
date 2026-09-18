"""`python wrap.py STATS -- ARGV...`: run ARGV, then write its exit code, wall time and peak memory (the
largest process in its tree, from RUSAGE_CHILDREN) to STATS as JSON, and exit with its code."""
import json
import resource
import subprocess
import sys
import time

if __name__ == "__main__":
    stats, argv = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
    start = time.monotonic()
    rc = subprocess.call(argv)
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    with open(stats, "w") as fh:
        json.dump({"rc": rc, "seconds": round(time.monotonic() - start, 1),
                   "peak_mb": round(peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024)}, fh)
    sys.exit(rc)
