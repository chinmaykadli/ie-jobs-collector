"""Canonical screening policy digest, not the raw file checksum."""
import sys,pathlib
from screen_policy import load_policy,validate
if __name__=="__main__":print(validate(load_policy(pathlib.Path(sys.argv[1]).read_text()))["sha256"])
