#!/usr/bin/env sh
set -eu

mkdir -p /tmp/oslab
cat /etc/os-release > /tmp/oslab/os-release.snapshot
echo "generic linux smoke fixture complete"

