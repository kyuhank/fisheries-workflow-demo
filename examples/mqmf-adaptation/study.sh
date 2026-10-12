#!/bin/sh
# Offline entry: only POSIX shell and Docker are needed on the host.
set -eu
case "$0" in
  */*) study_directory=${0%/*} ;;
  *) study_directory=. ;;
esac
study_root=$(CDPATH= cd -P "$study_directory" && pwd -P)
case "${1:-}" in
  prepare|baseline|update|fresh|wrong-scale|all|check) ;;
  *) printf '%s\n' 'Usage: sh study.sh prepare | baseline | update | fresh | wrong-scale | all | check' >&2; exit 2 ;;
esac
study_image=sha256:3f2b5d1eccea99114d3e089f281bdd531cbd2f1cfd8405d4f3b68722136c0158
study_upstream=ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker is required. Host R, Python, Make and Git are not required.' >&2; exit 2
fi
if ! study_inspect=$(docker image inspect "$study_image" --format '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"RootFS":{{json .RootFS}},"RepoDigests":{{json .RepoDigests}}}' 2>/dev/null); then
  printf '%s\n' 'The preserved SPC image is unavailable. Start Docker or load your previously verified v1.9.1 runtime archive using its preserved guide.' 'This study does not pull or build an image.' >&2; exit 2
fi
study_output=${STUDY_OUTPUT:-$study_root/../study-runs}
case "$study_output" in /*) ;; *) study_output=$study_root/$study_output ;; esac
case "$study_root$study_output" in *:*) printf '%s\n' 'Bind paths must not contain a colon.' >&2; exit 2 ;; esac
study_user=0:0
if command -v id >/dev/null 2>&1 && command -v mkdir >/dev/null 2>&1; then
  mkdir -p "$study_output"
  study_user=$(id -u):$(id -g)
fi
exec docker run --rm --pull never --platform linux/amd64 --network none --cpus 2 --memory 4g --user "$study_user" \
  --env "PAPER_OFFLINE_IMAGE_INSPECT=$study_inspect" --env "PAPER_RUNTIME_IMAGE=$study_upstream" \
  --env PAPER_RUNTIME_IMAGE_URL=https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow \
  --env PAPER_SOURCE_MODE=monorepo --env OMP_NUM_THREADS=2 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env "STUDY_READER=${STUDY_READER:-unspecified reader}" \
  -v "$study_root:/workspace:ro" -v "$study_output:/outputs" -w /workspace \
  "$study_image" python3 run-study.py "$@" --output /outputs
