"""Publish a structurally validated candidate to an immutable revision."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("writeback"))
