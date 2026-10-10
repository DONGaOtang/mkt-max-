"""Assemble actual module Markdown, with version and fingerprint metadata."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("assemble"))
