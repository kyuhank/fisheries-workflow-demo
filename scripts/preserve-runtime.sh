#!/bin/sh
# Preserve every image named by the saved run's runtime catalogue.
set -eu
case "$0" in */*) script_directory=${0%/*} ;; *) printf '%s\n' 'Run sh scripts/preserve-runtime.sh from an extracted release.' >&2; exit 2 ;; esac
root=$(CDPATH= cd -P "$script_directory/.." && pwd -P)
mode=save
case "${1:-}" in save|verify|load) mode=$1; shift ;; esac
if [ "$#" -ne 1 ]; then
  printf '%s\n' 'Usage: sh scripts/preserve-runtime.sh [save|verify|load] /absolute/runtime-copy' >&2
  exit 2
fi
exec Rscript --vanilla "$root/scripts/offline.R" "archive-$mode" "$1"
