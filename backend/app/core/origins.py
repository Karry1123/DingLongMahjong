"""Shared HTTP/WS origin policy for production sites and local LAN previews."""
from ipaddress import ip_address, ip_network
import re
from urllib.parse import urlsplit
from starlette.middleware.cors import CORSMiddleware

_LAN_NETWORKS = tuple(ip_network(network) for network in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7", "fe80::/10",
))


def is_local_origin(origin):
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False
        if parsed.hostname == "localhost":
            return True
        address = ip_address(parsed.hostname or "")
        return address.is_loopback or any(address in network for network in _LAN_NETWORKS)
    except ValueError:
        return False


def origin_allowed(origin, allowed_origins):
    return (origin in allowed_origins or "*" in allowed_origins or is_local_origin(origin)
            or bool(re.fullmatch(r"https://[a-zA-Z0-9-]+\.vercel\.app", origin)))


class LanCORSMiddleware(CORSMiddleware):
    def is_allowed_origin(self, origin):
        return origin_allowed(origin, self.allow_origins)
