"""Read-only arithmetic audit; unknown values and currency bases stay distinct."""
import sys
from hub_runtime import cli_main

if __name__ == "__main__":
    sys.exit(cli_main("cost_audit"))
