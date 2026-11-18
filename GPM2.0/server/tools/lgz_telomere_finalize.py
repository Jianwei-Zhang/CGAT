#!/usr/bin/env python3
"""Descriptive compatibility alias for the current LGZ terminal Step3."""
try:
    from lgz_step3 import *
except ModuleNotFoundError:
    from .lgz_step3 import *

if __name__ == "__main__":
    main()
