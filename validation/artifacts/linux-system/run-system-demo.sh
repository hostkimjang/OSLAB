#!/bin/sh
# OSLab Linux demo: write a commandResult JSON file that describes this guest.
# Usage: run-system-demo.sh OUTPUT_PATH
set -eu

output_path=$1
snapshot=/tmp/oslab/os-release.snapshot

# Print $1 as JSON string content: escape backslashes and quotes, join lines with \n.
json_text() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'
}

file_state() {
  if [ -e "$1" ]; then exists=true; else exists=false; fi
  printf '{ "path": "%s", "exists": %s }' "$(json_text "$1")" "$exists"
}

. /etc/os-release
kernel=$(uname -sr)
stdout="oslab linux system demo
kernel=$kernel
os=${PRETTY_NAME:-unknown}"

mkdir -p "$(dirname "$output_path")"
cat >"$output_path" <<EOF
{
  "schemaVersion": 1,
  "kind": "commandResult",
  "command": "linux system inventory",
  "exitCode": 0,
  "stdout": "$(json_text "$stdout")\n",
  "stderr": "",
  "metadata": {
    "kernel": "$(json_text "$kernel")",
    "osId": "$(json_text "${ID:-unknown}")",
    "osPrettyName": "$(json_text "${PRETTY_NAME:-unknown}")",
    "files": [
      $(file_state /etc/os-release),
      $(file_state "$snapshot")
    ]
  }
}
EOF
printf '%s\n' "$stdout"
