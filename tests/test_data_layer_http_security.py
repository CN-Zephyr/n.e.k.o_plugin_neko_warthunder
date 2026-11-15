from __future__ import annotations

import http.client
import importlib
import json
import threading
from contextlib import contextmanager


def _server_module():
    return importlib.import_module("neko_warthunder.data_layer.data_process.wt_server")


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


def _request(port, path, *, method="GET", headers=None, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers.setdefault("Content-Type", "application/json")
    connection.request(method, path, body=body, headers=headers)
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
        legacy, _headers, _body = _request(port, "/api/identity?name=Pilot", headers=action_header)
        assert legacy == 405
        assert service.player_name is None
        identity_denied, _headers, _body = _request(
            port, "/api/identity", method="POST", payload={"name": "Pilot"},
        )
        identity_ok, _headers, _body = _request(
            port,
            "/api/identity",
            method="POST",
            payload={"name": "Pilot"},
            headers=action_header,
        )
        spoofed, _headers, _body = _request(
            port, "/api/identity", method="POST", payload={"clear": True},
            headers={**action_header, "Origin": "https://example.invalid"},
        )
        wrong_type, _headers, _body = _request(
            port, "/api/identity", method="POST", payload={"clear": 1}, headers=action_header,
        )
        record_denied, _headers, _body = _request(port, "/api/record", method="POST", payload={"on": True})
        record_ok, _headers, record_body = _request(
            port,
            "/api/record",
            method="POST",
            payload={"on": True},
            headers=action_header,
        )

    assert identity_denied == 403
    assert identity_ok == 200
    assert spoofed == 403
    assert wrong_type == 400
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
