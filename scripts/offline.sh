#!/bin/sh
# Docker and POSIX shell entry; all Python/Make/R/Quarto runs inside the image.
set -eu
case "$0" in
  */*) script_directory=${0%/*} ;;
  *) printf '%s\n' 'Run sh scripts/offline.sh from an extracted release folder.' >&2; exit 2 ;;
esac
root=$(CDPATH= cd -P "$script_directory/.." && pwd -P)
image=sha256:3f2b5d1eccea99114d3e089f281bdd531cbd2f1cfd8405d4f3b68722136c0158
upstream=ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
if [ "$#" -eq 0 ]; then
  printf '%s\n' 'Usage: sh scripts/offline.sh run | job JOB | reproduce [JOB] | compare [JOB] | check' \
    'Results: ./offline-runs (choose another directory with PAPER_OFFLINE_OUTPUT).' >&2
  exit 2
fi
case "$1" in run|job|reproduce|compare|check) ;; *) printf '%s\n' 'Unknown offline command.' >&2; exit 2 ;; esac
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker is required. No host Python, Make or Git is required.' >&2; exit 2
fi
if ! inspect=$(docker image inspect "$image" --format '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"RootFS":{{json .RootFS}},"RepoDigests":{{json .RepoDigests}}}' 2>/dev/null); then
  printf '%s\n' 'The preserved SPC image is not available in the local Docker daemon.' \
    'Start Docker, or restore the separately preserved runtime with:' \
    '  sh scripts/preserve-runtime.sh load /absolute/preservation-folder' \
    'This command never pulls an image or accesses GitHub.' >&2
  exit 2
fi
output=${PAPER_OFFLINE_OUTPUT:-$root/offline-runs}
case "$output" in /*) ;; *) output=$root/$output ;; esac
case "$root$output" in *:*) printf '%s\n' 'Docker bind paths must not contain a colon.' >&2; exit 2 ;; esac
# Optional POSIX utilities keep caller ownership. With only Docker and shell,
# Docker creates the destination and writes it as root; the files remain readable.
user_option=0:0
if command -v id >/dev/null 2>&1 && command -v mkdir >/dev/null 2>&1; then
  mkdir -p "$output"
  user_option=$(id -u):$(id -g)
fi
exec docker run --rm --pull never --platform linux/amd64 --network none --cpus 2 --memory 4g --user "$user_option" \
  --env "PAPER_OFFLINE_IMAGE_INSPECT=$inspect" --env "PAPER_RUNTIME_IMAGE=$upstream" \
  --env PAPER_RUNTIME_IMAGE_URL=https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow \
  --env PAPER_SOURCE_MODE=multi-repository --env PAPER_SOURCE_LOCK=/workspace/source-lock.json \
  --env OMP_NUM_THREADS=2 \
  --env "PAPER_OFFLINE_READER=${PAPER_OFFLINE_READER:-unspecified reader}" \
  -v "$root:/workspace:ro" -v "$output:/outputs" -w /workspace \
  "$image" python3 scripts/offline-runtime.py "$@"
