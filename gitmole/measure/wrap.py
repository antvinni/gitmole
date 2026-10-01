"""`python wrap.py STATS -- ARGV...`: run ARGV, then write its exit code, times and peak memory to STATS as
JSON, and exit with its code. `seconds` is monotonic and stops while the machine sleeps; `wall_seconds` is
the clock and does not, so a sleep inside the run shows as their gap. `cpu_seconds` is the user and system
time of the process tree, and `peak_mb` its largest process (both from RUSAGE_CHILDREN)."""
import json
import resource
import subprocess
import sys
import time

if __name__ == "__main__":
    stats, argv = sys.argv[1], sys.argv[sys.argv.index("--") + 1:]
    start, wall = time.monotonic(), time.time()
    rc = subprocess.call(argv)
    seconds, wall = time.monotonic() - start, time.time() - wall
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak = usage.ru_maxrss
    with open(stats, "w") as fh:
        json.dump({"rc": rc, "seconds": round(seconds, 1), "wall_seconds": round(wall, 1),
                   "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 1),
                   "peak_mb": round(peak / 1024 / 1024 if sys.platform == "darwin" else peak / 1024)}, fh)
    sys.exit(rc)
