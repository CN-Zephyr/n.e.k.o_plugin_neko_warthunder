from __future__ import annotations

import http.client
import importlib.util
import json
import pathlib
import sys
import threading
from contextlib import contextmanager


def _server_module():
    module_name = "neko_warthunder.__wt_server_security_test__"
    if module_name in sys.modules:
        return sys.modules[module_name]
    data_dir = pathlib.Path(__file__).resolve().parent.parent / "data_layer" / "data process"
    spec = importlib.util.spec_from_file_location(module_name, data_dir / "wt_server.py")
    assert spec and spec.loader
    old_path = list(sys.path)
    sys.path.insert(0, str(data_dir))
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    return module


class _Recorder:
    def __init__(self) -> None:
        self.recording = False

    def status(self):
        return {"recording": self.recording}

    def start(self):
        self.recording = True
        return self.status()

    def stop(self):
        self.recording = False
        return self.status()


class _Service:
    def __init__(self) -> None:
        self.player_name = None
        self.recorder = _Recorder()

    def get_health(self):
        return {"ok": True}

    def get_snapshot(self):
        return {"state": "not_in_battle"}

    def get_part(self, name):
        if name == "combat":
            return {"self": None, "player_name": self.player_name}
        return {}

    def set_player_name(self, name):
        self.player_name = name

    def get_identity(self):
        return {"self": None, "player_name": self.player_name}

    def get_map(self):
        return None, None


@contextmanager
def _running_server(*, cors_origins=()):
    module = _server_module()
    server = module.create_http_server("127.0.0.1", 0, cors_origins=cors_origins)
    service = _Service()
    server.service = service
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _request(port, path, *, method="GET", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), json.loads(body or b"{}")
    connection.close()
    return result


def test_cross_origin_reads_are_not_exposed_by_default():
    with _running_server() as (port, _service):
        status, headers, body = _request(
            port,
            "/api/telemetry",
            headers={"Origin": "https://example.invalid"},
        )

    assert status == 200
    assert body["state"] == "not_in_battle"
    assert "Access-Control-Allow-Origin" not in headers


def test_explicit_cors_origin_is_echoed_and_preflight_is_limited():
    origin = "http://127.0.0.1:48911"
    with _running_server(cors_origins=(origin,)) as (port, _service):
        status, headers, _body = _request(port, "/api/telemetry", headers={"Origin": origin})
        denied, denied_headers, _body = _request(
            port,
            "/api/telemetry",
            method="OPTIONS",
            headers={"Origin": "https://example.invalid"},
        )

    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == origin
    assert denied == 403
    assert "Access-Control-Allow-Origin" not in denied_headers


def test_mutating_endpoints_require_action_header():
    action_header = {"X-Neko-Warthunder-Action": "1"}
    with _running_server() as (port, service):
        identity_denied, _headers, _body = _request(port, "/api/identity?name=Pilot")
        identity_ok, _headers, _body = _request(
            port,
            "/api/identity?name=Pilot",
            headers=action_header,
        )
        record_denied, _headers, _body = _request(port, "/api/record?on=1")
        record_ok, _headers, record_body = _request(
            port,
            "/api/record?on=1",
            headers=action_header,
        )

    assert identity_denied == 403
    assert identity_ok == 200
    assert service.player_name == "Pilot"
    assert record_denied == 403
    assert record_ok == 200
    assert record_body["recording"] is True


def test_loopback_server_rejects_non_loopback_host_header():
    with _running_server() as (port, _service):
        status, _headers, body = _request(
            port,
            "/api/telemetry",
            headers={"Host": "attacker.example"},
        )

    assert status == 403
    assert body == {"error": "host_not_allowed"}
