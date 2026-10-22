#!/bin/sh
# R, Make and locally restored Docker images run the complete browser workflow.
set -eu
case "$0" in */*) script_directory=${0%/*} ;; *) printf '%s\n' 'Run sh scripts/local.sh from an extracted release.' >&2; exit 2 ;; esac
root=$(CDPATH= cd -P "$script_directory/.." && pwd -P)
exec Rscript --vanilla "$root/scripts/run-local.R" "$@"
