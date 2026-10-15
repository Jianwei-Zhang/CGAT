#!/usr/bin/env bash
set -euo pipefail

export GPM_FAST_WORK_ROOT=__GPM_FAST_WORK_ROOT__
export GPM_FAST_THREADS=__GPM_FAST_THREADS__
export GPM_FAST_MINIMAP_PRESET=__GPM_FAST_MINIMAP_PRESET__
export GPM_FAST_SELF_MIN_CHAIN_SCORE=__GPM_FAST_SELF_MIN_CHAIN_SCORE__
export GPM_FAST_SELF_MINIMIZERS=__GPM_FAST_SELF_MINIMIZERS__

python3 "${GPM_FAST_WORK_ROOT}/.prepare_lib/tools/assign_chr_groups.py"
python3 "${GPM_FAST_WORK_ROOT}/.prepare_lib/tools/track_member_order.py" \
  --server-dir "${GPM_FAST_WORK_ROOT}"
