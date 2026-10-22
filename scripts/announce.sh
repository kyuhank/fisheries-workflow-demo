#!/bin/sh
# Show runner setup before the host R packages and job images are ready.
set +x
umask 077
announce_dir=$(mktemp -d)
trap 'rm -rf "$announce_dir"' EXIT HUP INT TERM
announce() {
  test -n "$PAPER_REQUEST_ID" && test -n "$ACTIONS_ID_TOKEN_REQUEST_URL" && test -n "$ACTIONS_ID_TOKEN_REQUEST_TOKEN" || return 1
  printf 'header = "Authorization: Bearer %s"\n' "$ACTIONS_ID_TOKEN_REQUEST_TOKEN" > "$announce_dir/identity.conf"
  case "$ACTIONS_ID_TOKEN_REQUEST_URL" in *\?*) announce_separator='&' ;; *) announce_separator='?' ;; esac
  curl --silent --show-error --fail --max-time 8 --config "$announce_dir/identity.conf" \
    "${ACTIONS_ID_TOKEN_REQUEST_URL}${announce_separator}audience=fisheries-paper-demo" --output "$announce_dir/identity.json" 2>/dev/null || return 1
  announce_token=$(jq -er '.value | select(type == "string" and test("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$"))' "$announce_dir/identity.json") || return 1
  printf 'header = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\n' "$announce_token" > "$announce_dir/runner.conf"
  announce_api='https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api/runner'
  curl --silent --show-error --fail --max-time 8 --config "$announce_dir/runner.conf" \
    "$announce_api/context?request=$PAPER_REQUEST_ID" --output "$announce_dir/context.json" 2>/dev/null || return 1
  announce_operation=$(cat /proc/sys/kernel/random/uuid)
  jq -n --arg operation "$announce_operation" '{operation_id:$operation,event:{state:"phase",title:"Preparing host R",message:"The GitHub runner has started. It is preparing R before retrieving the job software."}}' > "$announce_dir/event.json"
  curl --silent --show-error --fail --max-time 8 --config "$announce_dir/runner.conf" \
    --data-binary "@$announce_dir/event.json" "$announce_api/event?request=$PAPER_REQUEST_ID" --output "$announce_dir/response.json" 2>/dev/null || return 1
}
if ! announce; then
  printf '%s\n' 'Setup status is temporarily unavailable; continuing with the registered execution.'
fi
