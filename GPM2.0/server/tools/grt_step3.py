#!/usr/bin/env python3
"""Compatibility forwarding module; the implementation lives under LGZ."""
try:
    from lgz_compat import forward_module as _forward_module
except ModuleNotFoundError:
    from .lgz_compat import forward_module as _forward_module

_forward_module(__name__, __package__, globals())
