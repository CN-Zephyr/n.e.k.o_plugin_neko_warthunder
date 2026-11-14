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
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", _ACTION_HEADER)
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
        path = urlparse(self.path).path.rstrip("/") or "/"

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
            # 查看/设置“自己是谁”。?name=昵称 设手动昵称(权威)；?clear=1 清除回退自动。
            q = parse_qs(urlparse(self.path).query)
            if ("clear" in q or q.get("name")) and not self._action_allowed():
                return
            requested: Any = "(unchanged)"
            if "clear" in q:
                self.service.set_player_name(None)
                requested = None
            elif q.get("name"):
                requested = q["name"][0]
                self.service.set_player_name(requested)
            identity = self.service.get_identity()
            self._send_json({
                "requested": requested,
                "note": "手动身份立即持久显示；战绩归属将在下一次 events 轮询（≤event-interval）后应用",
                **identity,
            })
            return

        if path == "/api/faction_colors":
            # 查看/设置小地图敌我颜色。?ally=%23174DFF&enemy=%23FA0C00；颜色过近时 conflict=true。
            q = parse_qs(urlparse(self.path).query)
            ally = (q.get("ally") or [None])[0]
            enemy = (q.get("enemy") or [None])[0]
            if ally is None and enemy is None:
                self._send_json(self.service.get_faction_colors())
                return
            if not self._action_allowed():
                return
            if (ally is not None and parse_hex_color(ally) is None) or (
                enemy is not None and parse_hex_color(enemy) is None
            ):
                self._send_json({"error": "invalid_color", **self.service.get_faction_colors()}, 400)
                return
            self._send_json(self.service.set_faction_colors(ally, enemy))
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
            # 调试开关：?on=1 开始转存 / ?on=0 停止 / 无参=查状态
            q = parse_qs(urlparse(self.path).query)
            if "on" in q and not self._action_allowed():
                return
            rec = self.service.recorder
            if "on" in q:
                want = q["on"][0].strip().lower() in ("1", "true", "yes", "on")
                status = rec.start() if want else rec.stop()
            else:
                status = rec.status()
            self._send_json(status)
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
