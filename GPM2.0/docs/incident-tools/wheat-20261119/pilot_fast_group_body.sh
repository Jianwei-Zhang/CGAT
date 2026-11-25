#!/bin/bash
# Invoked inside the explicitly bound 4D A or BC allocation, not a production stage.
set -euo pipefail
umask 077
mode=$1; [[ $mode == A || $mode == BC ]]; here=$PWD
base="$HOME/cgat-reads-debug/jm19-compare-614589f-20261118"; q="$base/q0-request-ready.44e274a7/qualification"
sha256sum -c --quiet kit.sha256
printf '%s  %s\n' 9fe4a884f98b500fa00c3ea1e6bfd62918a514507637c4793b0fe7b1d213703f "$q/group.py" 36b6c31cd0e5b0049b47646f96d2991081050d79d24b947c95a1aee645d6a70a "$q/fork_wheat_q0.py" 0f06edd183467d950cd99d5c11ca8ed23ff57aaeacce96a6580b7527573dac28 "$q/latest.tgz" | sha256sum -c --quiet -
set +u; source "$HOME/cgat-reads-debug/jm19-x86-readiness-20261118/environment.sh"; set -u
w=$(mktemp -d /tmp/wheat-fast4d.XXXXXXXX); trap 'rm -rf -- "$w"' EXIT
mkdir "$w/input" "$w/code"; tar -xzf "$q/latest.tgz" -C "$w/code"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH="$w/code/GPM2.0/server/tools" GPM_RUN_THREADS=8
python3 -Bu "$q/group.py" stage "$base" "$w/input"
for i in {1..120}; do [[ ! -s allocation.json ]] || break; sleep 2; done
[[ -s allocation.json ]]; export _GPM_Q0_SCHEDULER_PROOF="$here/allocation.json"; _GPM_Q0_SCHEDULER_SHA256=$(sha256sum allocation.json | cut -d ' ' -f1); export _GPM_Q0_SCHEDULER_SHA256
python3 -Bu pilot_fast_group_run.py "$mode" "$w/input" "$base" "$here/result"
sha256sum result/*.json result/*.fa.gz > results.sha256
cat results.sha256
