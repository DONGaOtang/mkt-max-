"""Initialize or resume a local MKT Max 1 project; does not start an agent."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("start"))
