"""Shared LGZ domain, I/O, path, alignment, replay, and checkpoint services."""

from .common import *
from .stage_schema import *
from .stage_io import *
from .stage_alignment import *
from .stage_replay import *
from .stage_cache import *
from .stage_metadata import *

# A targeted Q0 upgrade can run beside an immutable legacy outer runtime.
# Keep the real module/checkpoint machinery; supply only its missing I/O API.
from .q0_paf_io import install_legacy_paf_reader as _install_legacy_paf_reader
_install_legacy_paf_reader()
