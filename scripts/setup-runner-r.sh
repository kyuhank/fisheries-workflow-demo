#!/bin/sh
# The host coordinates jobs; Quarto and analysis packages stay in the job images.
set -eu
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04 && test "$(uname -m)" = x86_64 || {
  printf '%s\n' 'This installer requires the standard Ubuntu 24.04 AMD64 runner.' >&2
  exit 1
}
: "${RUNNER_TEMP:?GitHub runner temporary directory is required}"
: "${GITHUB_PATH:?GitHub PATH file is required}"
: "${GITHUB_ENV:?GitHub environment file is required}"

runner_r_version=4.5.1
runner_r_bin="/opt/R/$runner_r_version/bin"
runner_r_deb="$RUNNER_TEMP/fisheries-host-r.deb"
if ! test -x "$runner_r_bin/Rscript"; then
  trap 'rm -f "$runner_r_deb"' EXIT HUP INT TERM
  curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 --max-time 60 \
    "https://cdn.rstudio.com/r/ubuntu-2404/pkgs/r-${runner_r_version}_1_amd64.deb" \
    --output "$runner_r_deb"
  printf '%s  %s\n' '899c1b7e1875e4e46f0006f212772c6f9f1e4328fefd48eec2705fbabbb2b7f3' "$runner_r_deb" | sha256sum --check
  sudo env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends "$runner_r_deb"
fi
"$runner_r_bin/Rscript" --vanilla -e 'stopifnot(getRversion() == "4.5.1"); cat(R.version.string, "\n")'
runner_r_library="$RUNNER_TEMP/fisheries-host-library"
mkdir -p "$runner_r_library"
printf '%s\n' "$runner_r_bin" >> "$GITHUB_PATH"
printf 'R_LIBS_USER=%s\nRSPM=%s\n' "$runner_r_library" \
  'https://p3m.dev/cran/__linux__/noble/latest' >> "$GITHUB_ENV"
