from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .common import *

ENGINE_VERSION = 2

MIN_GAP_LENGTH = 100

FLANK_LENGTH = 10_000

MIN_ALIGNMENT_LENGTH = 1_000

MIN_IDENTITY = 0.40

MAX_FILL_LENGTH = 1_000_000

MIN_COMPONENT_LENGTH = 100_000

FILTER_CONNECTOR_LENGTH = 100

PRESET = "asm5"

USAGE_FIELDS = [
    "usage_id",
    "donor_set_id",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "stage",
    "status",
    "event_id",
    "final_path_segment_id",
    "reason",
]

ATTEMPT_FIELDS = [
    "attempt_id",
    "chr",
    "object_id",
    "stage",
    "status",
    "reason",
    "candidate_count",
    "accepted_event_id",
]

STAGE_FIELDS = [
    "stage",
    "q_input_version",
    "q_input_sha256",
    "q_output_version",
    "q_output_sha256",
    "donor_set_id",
    "status",
    "checkpoint_relpath",
    "checkpoint_sha256",
]

TOOL_FIELDS = ["tool", "version", "executable"]

CANDIDATE_FIELDS = [
    "candidate_id",
    "stage",
    "chr",
    "object_id",
    "member_id",
    "source_dataset",
    "source_contig",
    "source_start",
    "source_end",
    "orientation",
    "trim_left",
    "trim_right",
    "fill_length",
    "identity",
    "aligned_length",
    "mapq",
    "left_paf_line",
    "right_paf_line",
    "fragment_id",
    "donor_reuse",
    "donor_reuse_of",
]

ARBITRATION_FIELDS = CANDIDATE_FIELDS + ["outcome", "reason", "event_id", "final_path_segment_id"]

REJECTION_FIELDS = ["stage", "chr", "object_id", "left_paf_line", "right_paf_line", "reason"]
