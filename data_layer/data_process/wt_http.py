"""战雷遥测后台服务的 HTTP 接口。"""

from __future__ import annotations

import ipaddress
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

if __package__:
    from .wt_telemetry import parse_hex_color
    if TYPE_CHECKING:
        from .wt_server import TelemetryService
else:
    from wt_telemetry import parse_hex_color
    if TYPE_CHECKING:
        from wt_server import TelemetryService


_ACTION_HEADER = "X-Neko-Warthunder-Action"
_CONTENT_TYPE_BY_EXT = {"jpg": "image/jpeg", "png": "image/png"}
_MUTATION_QUERY_KEYS = {
    "/api/identity": {"name", "clear"},
    "/api/faction_colors": {"ally", "enemy"},
    "/api/record": {"on"},
}
_MAX_ACTION_BYTES = 4096


class _Handler(BaseHTTPRequestHandler):
    server_version = "WTTelemetry/2.0"

    @property
    def service(self) -> TelemetryService:
        return self.server.service  # type: ignore[attr-defined]

    def _cors(self) -> None:
        origin = str(self.headers.get("Origin") or "").strip()
        server = getattr(self, "server", None)
        allowed_origins = getattr(server, "cors_origins", frozenset()) if server else frozenset()
        if origin and origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", f"{_ACTION_HEADER}, Content-Type")
            self.send_header("Vary", "Origin")

    def _host_allowed(self) -> bool:
        bind_host = str(getattr(self.server, "bind_host", "")).strip().lower()
        if not _is_loopback_host(bind_host):
            return True
        try:
            request_host = urlparse(f"//{self.headers.get('Host', '')}").hostname or ""
        except ValueError:
            return False
        return _is_loopback_host(request_host)

    def _action_allowed(self) -> bool:
        if self.headers.get(_ACTION_HEADER) == "1":
            return True
        self._send_json({"error": "action_header_required"}, 403)
        return False

    def _send_json(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        if not self._host_allowed():
            self._send_json({"error": "host_not_allowed"}, 403)
            return
        origin = str(self.headers.get("Origin") or "").strip()
        allowed_origins = getattr(self.server, "cors_origins", frozenset())
        if origin and origin not in allowed_origins:
            self._send_json({"error": "origin_not_allowed"}, 403)
            return
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._send_json({"error": "host_not_allowed"}, 403)
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in _MUTATION_QUERY_KEYS and _MUTATION_QUERY_KEYS[path].intersection(
            parse_qs(parsed.query, keep_blank_values=True)
        ):
            self._send_json({"error": "use_post"}, 405)
            return

        if path in ("/", "/health", "/api/health"):
            self._send_json(self.service.get_health())
            return

        if path == "/api/telemetry":
            self._send_json(self.service.get_snapshot())
            return

        if path == "/api/processed":
            self._send_json(self.service.get_part("processed"))
            return

        if path == "/api/situation":
            self._send_json(self.service.get_part("situation"))
            return

        if path in ("/api/kills", "/api/combat"):
            self._send_json(self.service.get_part("combat"))
            return

        if path == "/api/identity":
            self._send_json({"requested": "(unchanged)", **self.service.get_identity()})
            return

        if path == "/api/faction_colors":
            self._send_json(self.service.get_faction_colors())
            return

        if path == "/api/notices":
            self._send_json(self.service.get_part("hud_notices"))
            return

        if path == "/api/awards":
            # 战斗嘉奖（一血/双杀/三杀/连续无伤歼敌等）；?notable=1 仅返回高光子集
            q = parse_qs(urlparse(self.path).query)
            awards = self.service.get_part("awards") or {}
            if q.get("notable"):
                awards = {**awards, "feed": awards.get("notable", [])}
            self._send_json(awards)
            return

        if path == "/api/record":
            self._send_json(self.service.recorder.status())
            return

        if path == "/api/proximity":
            self._send_json(self.service.get_part("proximity"))
            return

        if path == "/api/alerts":
            processed = self.service.get_part("processed")
            alerts = processed.get("alerts", []) if isinstance(processed, dict) else []
            level = processed.get("level") if isinstance(processed, dict) else None
            self._send_json({"level": level, "alerts": alerts})
            return

        if path in ("/api/map.jpg", "/api/map"):
            data, ext = self.service.get_map()
            if not data:
                self._send_json({"error": "no map available"}, 404)
                return
            ctype = _CONTENT_TYPE_BY_EXT.get(ext or "", "application/octet-stream")
            self._send_bytes(data, ctype)
            return

        subset_keys = {
            "/api/state": "vehicle",
            "/api/indicators": "indicators",
            "/api/map_objects": "map_objects",
            "/api/map_info": "map_info",
            "/api/hud": "hud_events",
            "/api/chat": "chat",
        }
        if path in subset_keys:
            self._send_json(self.service.get_part(subset_keys[path]))
            return

        self._send_json({"error": "not found", "path": path}, 404)

    def do_POST(self) -> None:
        if not self._host_allowed():
            self._send_json({"error": "host_not_allowed"}, 403)
            return
        path = urlparse(self.path).path.rstrip("/")
        if path not in _MUTATION_QUERY_KEYS:
            self._send_json({"error": "not found"}, 404)
            return
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.cors_origins:
            self._send_json({"error": "origin_not_allowed"}, 403)
            return
        if not self._action_allowed():
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json({"error": "json_required"}, 415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= _MAX_ACTION_BYTES:
                raise ValueError
            self.connection.settimeout(2)
            body = json.loads(self.rfile.read(length))
        except (ValueError, OSError):
            self._send_json({"error": "invalid_body"}, 400)
            return
        if not isinstance(body, dict) or not body or body.keys() - _MUTATION_QUERY_KEYS[path]:
            self._send_json({"error": "invalid_body"}, 400)
            return
        if path == "/api/identity":
            name = body.get("name")
            if set(body) == {"clear"} and body["clear"] is True:
                name = None
            elif set(body) != {"name"} or not isinstance(name, str) or not name.strip() or "\x00" in name:
                self._send_json({"error": "invalid_identity"}, 400)
                return
            self.service.set_player_name(name)
            self._send_json({"requested": name, **self.service.get_identity()})
        elif path == "/api/faction_colors":
            if any(not isinstance(color, str) or parse_hex_color(color) is None for color in body.values()):
                self._send_json({"error": "invalid_color", **self.service.get_faction_colors()}, 400)
                return
            self._send_json(self.service.set_faction_colors(body.get("ally"), body.get("enemy")))
        else:
            want = body["on"]
            if type(want) is not bool:
                self._send_json({"error": "invalid_record_state"}, 400)
                return
            rec = self.service.recorder
            self._send_json(rec.start() if want else rec.stop())

    def log_message(self, *args: Any) -> None:
        pass


def _is_loopback_host(host: str) -> bool:
    value = str(host or "").strip().lower()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def create_http_server(host: str, port: int, *, cors_origins: list[str] | tuple[str, ...] = ()):
    server_class = ThreadingHTTPServer
    if ":" in host:
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_class = IPv6ThreadingHTTPServer
    server = server_class((host, port), _Handler)
    server.bind_host = host  # type: ignore[attr-defined]
    server.cors_origins = frozenset(  # type: ignore[attr-defined]
        str(origin).strip() for origin in cors_origins if str(origin).strip()
    )
    return server
