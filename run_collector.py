import subprocess
subprocess.run(["python3", "supplemental_discovery.py", "--test"], check=True)
import json, argparse, pathlib
import ingest
import ats_extra
a=argparse.ArgumentParser();a.add_argument("--sources",default="sources.json");a.add_argument("--output",default="output-private-baseline");args=a.parse_args();print(json.dumps(ats_extra.run(json.loads(pathlib.Path(args.sources).read_text()),args.output),indent=2))

import supplemental_discovery
supplemental_discovery.run(args.output)
