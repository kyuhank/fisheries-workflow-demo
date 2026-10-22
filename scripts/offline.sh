#!/bin/sh
# Forward reader commands to the preserved host R tools.
set -eu
case "$0" in */*) script_directory=${0%/*} ;; *) printf '%s\n' 'Run sh scripts/offline.sh from an extracted release folder.' >&2; exit 2 ;; esac
root=$(CDPATH= cd -P "$script_directory/.." && pwd -P)
exec Rscript --vanilla "$root/scripts/offline.R" "$@"
