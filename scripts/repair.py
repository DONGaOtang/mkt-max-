"""Rebuild derived views after validation; never force-unlocks projects."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("repair"))
