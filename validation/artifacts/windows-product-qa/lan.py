"""Reach the Proxmox node over the local network with certificate checks.

The configured API endpoint provides the cluster CA. LAN connections then use
the node name from the certificate and verify it against that CA. Child
processes inherit the route through environment variables.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import quote

ADDRESS = "OSLAB_LAN_ADDRESS"
NAME = "OSLAB_LAN_NAME"
AUTHORITY = "OSLAB_LAN_CA"


def apply_from_environment():
    """Resolve the node name to its LAN address and trust the cluster CA in this process."""
    address, name, authority = os.environ.get(ADDRESS), os.environ.get(NAME), os.environ.get(AUTHORITY)
    if not address or not name or not authority or getattr(socket.getaddrinfo, "oslab_lan", False):
        return
    resolve = socket.getaddrinfo

    def routed(host, *args, **kwargs):
        return resolve(address if host == name else host, *args, **kwargs)

    routed.oslab_lan = True
    socket.getaddrinfo = routed
    create_context = ssl.create_default_context

    def trusted_context(*args, **kwargs):
        context = create_context(*args, **kwargs)
        context.load_verify_locations(cafile=authority)
        return context

    # urllib and asyncio both build their client contexts through these functions.
    ssl.create_default_context = trusted_context
    ssl._create_default_https_context = trusted_context
    # urllib keeps the context of its first opener, so build a new opener.
    urllib.request.install_opener(None)


def prepare(client, config_path, output_root, output, address, port=8006):
    """Write the cluster CA and a LAN config, then route this process and its children."""
    node = client.config.node
    certificates = client.request("GET", f"/nodes/{quote(node, safe='')}/certificates/info")
    authority = next(row["pem"] for row in certificates if row.get("filename") == "pve-root-ca.pem")
    names = next(row.get("san") or [] for row in certificates if row.get("filename") == "pve-ssl.pem")
    if node not in names:
        raise RuntimeError("The node certificate does not list the node name")
    ca_file = output / "pve-root-ca.pem"
    ca_file.write_text(authority, encoding="ascii")

    text = Path(config_path).read_text(encoding="utf-8")
    api = re.compile(r"^(\s*)apiUrl:.*$", re.MULTILINE)
    root = re.compile(r"^(\s*)outputRoot:.*$", re.MULTILINE)
    if len(api.findall(text)) != 1 or len(root.findall(text)) != 1:
        raise RuntimeError("Expected one apiUrl and one outputRoot setting in the OSLab config")
    text = api.sub(lambda match: f'{match[1]}apiUrl: "https://{node}:{port}"', text)
    # Keep VMID reservations in the same lock directory as other OSLab runs.
    text = root.sub(lambda match: f"{match[1]}outputRoot: {json.dumps(str(Path(output_root).resolve()))}", text)
    lan_config = output / "oslab.lan.yaml"
    lan_config.write_text(text, encoding="utf-8")

    os.environ.update({ADDRESS: address, NAME: node, AUTHORITY: str(ca_file)})
    apply_from_environment()
    return lan_config


if __name__ == "__main__":
    # Serve OSLab computer use over the LAN route: python lan.py --config ... --vm-id ...
    apply_from_environment()
    from oslab.mcp_server import main

    raise SystemExit(main())
