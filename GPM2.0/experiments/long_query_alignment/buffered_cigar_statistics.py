"""Compatibility import for isolated buffered-check replay and scalar-oracle tests.

Production keeps the implementation in windowed_alignment so existing packaged
runtime dependency lists do not acquire an optional experiment module.
"""
from windowed_alignment import MAX_BUFFER_BYTES, checked_statistics
