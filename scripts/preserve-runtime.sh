#!/bin/sh
# Save/restore the exact image using Docker and Python contained in that image.
set -eu
case "$0" in */*) script_directory=${0%/*} ;; *) printf '%s\n' 'Run sh scripts/preserve-runtime.sh from the source folder.' >&2; exit 2 ;; esac
root=$(CDPATH= cd -P "$script_directory/.." && pwd -P)
image=sha256:3f2b5d1eccea99114d3e089f281bdd531cbd2f1cfd8405d4f3b68722136c0158
mode=save
case "${1:-}" in verify|load) mode=$1; shift ;; esac
if [ "$#" -ne 1 ]; then
  printf '%s\n' 'Usage: sh scripts/preserve-runtime.sh [verify|load] /absolute/preservation-folder' >&2; exit 2
fi
directory=$1
case "$directory" in /*) ;; *) directory=$root/$directory ;; esac
case "$root$directory" in *:*) printf '%s\n' 'Docker bind paths must not contain a colon.' >&2; exit 2 ;; esac
if ! command -v docker >/dev/null 2>&1; then printf '%s\n' 'Docker is required; no host Python or gzip is required.' >&2; exit 2; fi
if [ "$mode" = load ]; then
  # A fresh host has no trusted Python runtime yet. Docker loads the explicitly
  # supplied archive first; full checks follow before any analysis can run.
  printf '%s\n' 'Loading the supplied local archive; checksum/config/layer checks follow before analysis.' >&2
  docker image load --input "$directory/fisheries-workflow-runtime.tar.gz"
fi
if ! inspect=$(docker image inspect "$image" --format '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}},"RootFS":{{json .RootFS}},"RepoDigests":{{json .RepoDigests}}}' 2>/dev/null); then
  printf '%s\n' 'The exact SPC config ID is absent, or Docker is not running. Nothing was pulled.' \
    'Restore a preserved archive using the load command. Save/verify require the exact image locally.' >&2; exit 2
fi
if [ "$mode" = save ]; then
  # Pipeline errors cannot masquerade as success: archive-save checks the complete
  # Docker manifest, config bytes and all ordered layer bytes after reading stdin.
  docker image save "$image" | docker run --rm -i --pull never --platform linux/amd64 \
    --network none --cpus 2 --memory 2g --env "PAPER_OFFLINE_IMAGE_INSPECT=$inspect" \
    -v "$root:/workspace:ro" -v "$directory:/outputs" -w /workspace \
    "$image" python3 scripts/offline-runtime.py archive-save
else
  exec docker run --rm --pull never --platform linux/amd64 --network none --cpus 2 --memory 2g \
    --env "PAPER_OFFLINE_IMAGE_INSPECT=$inspect" \
    -v "$root:/workspace:ro" -v "$directory:/outputs:ro" -w /workspace \
    "$image" python3 scripts/offline-runtime.py archive-verify
fi
