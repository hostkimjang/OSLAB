#!/bin/sh
# Recreates what Demo Agent 2.3.1 leaves on a registered Ubuntu machine so the
# upgrade scenario starts from the previous release: the program files, the INI
# config, and the schema 1 state that holds the asset registration.
set -eu

root="${DEMO_AGENT_ROOT:-}"
manifest="${1:-/opt/oslab/demo-agent-2.3.1-fixture.json}"
version="2.3.1"
asset_id="8c1e5f3a-7b20-4d96-a4e8-2f9b6c0d1e73"
asset_name="demo-ubuntu-upgrade"
server_url="https://inventory.example.invalid"
registered_at="2026-08-05T02:41:09Z"

mkdir -p "$root/opt/demo-agent/bin" "$root/usr/local/bin" "$root/etc/demo-agent" \
  "$root/var/lib/demo-agent" "$root/var/log/demo-agent" "$(dirname "$manifest")"

printf '%s\n' "$version" > "$root/opt/demo-agent/VERSION"
printf '#!/bin/sh\necho "Demo Agent %s"\n' "$version" > "$root/opt/demo-agent/bin/demo-agent"
chmod 755 "$root/opt/demo-agent/bin/demo-agent"
ln -sf /opt/demo-agent/bin/demo-agent "$root/usr/local/bin/demo-agent"

cat > "$root/etc/demo-agent/agent.conf" <<EOF
; Demo Agent 2.3 configuration
[server]
url = $server_url

[scan]
interval_hours = 6
exclude = /tmp;/var/tmp
EOF

cat > "$root/var/lib/demo-agent/state.json" <<EOF
{
  "schemaVersion": 1,
  "kind": "demoAgentState",
  "registered": true,
  "assetId": "$asset_id",
  "assetName": "$asset_name",
  "serverUrl": "$server_url",
  "registeredAtUtc": "$registered_at",
  "lastScanUtc": "2026-11-18T21:00:11Z",
  "lastScanRecords": 598
}
EOF

cat > "$root/var/log/demo-agent/agent.log" <<EOF
$registered_at INFO register asset=$asset_name id=$asset_id
2026-11-18T21:00:11Z INFO scan records=598
EOF

cat > "$manifest" <<EOF
{
  "schemaVersion": 1,
  "kind": "fixtureResult",
  "ready": true,
  "fixture": "demo-agent-2.3.1-installed",
  "product": "Demo Agent",
  "version": "$version",
  "registration": {
    "assetId": "$asset_id",
    "assetName": "$asset_name",
    "serverUrl": "$server_url",
    "registeredAtUtc": "$registered_at"
  },
  "paths": {
    "programDir": "$root/opt/demo-agent",
    "config": "$root/etc/demo-agent/agent.conf",
    "state": "$root/var/lib/demo-agent/state.json"
  }
}
EOF

echo "Demo Agent $version installed and registered as $asset_name ($asset_id)"
