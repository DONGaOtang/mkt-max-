"""Restore content as a new revision while retaining current real events."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("rollback"))
