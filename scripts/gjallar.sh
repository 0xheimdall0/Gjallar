#!/usr/bin/env sh
#
# Gjallar client for Linux and macOS. Needs only curl.
#
#   export GJALLAR_URL=https://gjallar.example.com
#   export GJALLAR_TOKEN=sig_your_source_token
#
#   gjallar.sh event "Backup finished" -m "412 GB in 3m21s" -s info -t backup
#   gjallar.sh ping nightly-backup --every 86400 --grace 3600
#
# Put those two exports in ~/.profile (or the crontab) once, and every script on
# the machine can report with a single line.
#
# Reporting never fails the caller: if Gjallar is unreachable this prints a
# warning and exits 0, so a backup script is never broken by its own logging.

set -eu

URL="${GJALLAR_URL:-http://127.0.0.1:8000}"
TOKEN="${GJALLAR_TOKEN:-}"

if [ -z "$TOKEN" ]; then
    echo "gjallar: GJALLAR_TOKEN is not set" >&2
    exit 1
fi

# Escape a string for embedding in JSON: backslashes, quotes, then newlines.
json_string() {
    printf '"%s"' "$(
        printf '%s' "$1" |
            sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a' -e 'N' -e '$!ba' -e 's/\n/\\n/g'
    )"
}

post() {
    # $1 = path, $2 = json body
    if ! curl -fsS -X POST "$URL$1" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$2" >/dev/null 2>&1
    then
        echo "gjallar: could not reach $URL$1" >&2
    fi
}

usage() {
    sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

command="${1:-}"
[ -n "$command" ] || usage
shift || true

case "$command" in
event)
    title="${1:-}"
    [ -n "$title" ] || usage
    shift

    severity="info"
    message=""
    tags=""

    while [ $# -gt 0 ]; do
        case "$1" in
            -s|--severity) severity="$2"; shift 2 ;;
            -m|--message)  message="$2";  shift 2 ;;
            -t|--tag)
                # Repeatable: -t backup -t nightly
                if [ -z "$tags" ]; then tags="$(json_string "$2")"
                else tags="$tags,$(json_string "$2")"; fi
                shift 2 ;;
            *) usage ;;
        esac
    done

    body="{\"title\":$(json_string "$title"),\"severity\":$(json_string "$severity")"
    [ -n "$message" ] && body="$body,\"message\":$(json_string "$message")"
    [ -n "$tags" ] && body="$body,\"tags\":[$tags]"
    body="$body}"

    post "/api/events" "$body"
    ;;

ping)
    name="${1:-}"
    [ -n "$name" ] || usage
    shift

    every=""
    grace=""

    while [ $# -gt 0 ]; do
        case "$1" in
            -e|--every) every="$2"; shift 2 ;;
            -g|--grace) grace="$2"; shift 2 ;;
            *) usage ;;
        esac
    done

    body="{"
    [ -n "$every" ] && body="$body\"expected_interval_seconds\":$every"
    if [ -n "$grace" ]; then
        [ -n "$every" ] && body="$body,"
        body="$body\"grace_seconds\":$grace"
    fi
    body="$body}"

    post "/api/heartbeats/$name/ping" "$body"
    ;;

*)
    usage
    ;;
esac
