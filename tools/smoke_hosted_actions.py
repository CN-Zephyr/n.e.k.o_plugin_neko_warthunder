"""Check an installed package's first Hosted UI context in a real SDK worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import tomllib
from pathlib import Path


async def check(package: Path, sandbox: Path, *, host_route: bool) -> None:
    from plugin.core import host as host_module
    from plugin.core.host import PluginHost, _import_plugin_module
    from plugin.core.registry import scan_static_metadata
    from plugin.core.state import state
    from plugin.core.ui_manifest import normalize_plugin_ui_manifest
    from plugin.logging_config import logger
    from plugin.neko_plugin_cli.core import install_package
    from plugin.server.application.plugins.ui_query_service import PluginUiQueryService

    plugin_id = "neko_warthunder"
    plugins = sandbox / "plugins"
    installed = install_package(package, plugins_root=plugins, on_conflict="fail")
    if installed.payload_hash_verified is not True:
        raise RuntimeError("installed payload was not verified")
    manifest = plugins / plugin_id / "plugin.toml"
    # Adjust only the temporary installation. This smoke needs no game, telemetry or TTS.
    text = manifest.read_text(encoding="utf-8")
    config = tomllib.loads(text)
    if config[plugin_id]["data_layer_auto_start"] is not True:
        raise RuntimeError("unrecognized data layer startup default")
    text = text.replace("data_layer_auto_start = true", "data_layer_auto_start = false")
    text = text.replace("http://127.0.0.1:8112", "http://127.0.0.1:1")
    config = tomllib.loads(text)
    if config[plugin_id]["data_layer_auto_start"] or config[plugin_id]["data_layer_url"] != "http://127.0.0.1:1":
        raise RuntimeError("temporary configuration did not isolate telemetry")
    manifest.write_text(text, encoding="utf-8")
    meta = config["plugin"]
    module = _import_plugin_module("plugins.neko_warthunder", manifest, logger)
    if Path(module.__file__).resolve() != manifest.with_name("__init__.py").resolve():
        raise RuntimeError("worker did not resolve the temporary installation")
    scan_static_metadata(plugin_id, module.NekoWarthunderPlugin, config, meta)
    with state.acquire_plugins_write_lock():
        state.plugins[plugin_id] = {
            "id": plugin_id,
            "config_path": str(manifest),
            "plugin_ui": normalize_plugin_ui_manifest(config, plugin_id=plugin_id),
        }
    state.invalidate_snapshot_cache("plugins")
    # This one-shot host has no desktop lifecycle. Keep its storage rooted in sandbox.
    host_module._refresh_child_storage_layout_env = lambda _logger: None
    host = PluginHost(plugin_id, meta["entry"], manifest)
    with state.acquire_plugin_hosts_write_lock():
        state.plugin_hosts[plugin_id] = host
    service = PluginUiQueryService()
    try:
        await host.start(startup_timeout=40, startup_failure="fail")
        if host_route:
            context = await service.get_surface_context(plugin_id, kind="panel", surface_id="main")
        else:
            context = await host.get_ui_context("dashboard")
        required = {"test_say", "set_dry_run", "pause", "resume"}
        for field in ("actions", "entries") if host_route else ("actions",):
            missing = required - {item["id"] for item in context[field]}
            if missing:
                raise RuntimeError(f"first context missing {field}: {sorted(missing)}")
        if context["state"]["dry_run"] is not True:
            raise RuntimeError("fresh install did not start in dry-run")
        for value in (False, True):
            args = {"value": value}
            if host_route:
                result = (await service.call_surface_action(plugin_id, action_id="set_dry_run", args=args))["result"]
            else:
                result = await host.trigger("set_dry_run", args, timeout=5)
            if result["dry_run"] is not value:
                raise RuntimeError("first-start action did not change dry-run")
        print("Hosted UI first-start smoke passed")
    finally:
        await host.shutdown(timeout=5)
        if host.is_alive():
            raise RuntimeError("SDK worker did not stop")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--host-route", action="store_true", help="Also verify the host's Hosted UI route service.")
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    with tempfile.TemporaryDirectory(prefix="wt-hosted-smoke-") as tmp:
        sandbox = Path(tmp)
        os.environ.update({
            "PLUGIN_CONFIG_ROOT": str(sandbox / "plugins"),
            "NEKO_STORAGE_SELECTED_ROOT": str(sandbox / "runtime"),
            "NEKO_STORAGE_ANCHOR_ROOT": str(sandbox / "runtime"),
            "_NEKO_MAIN_SERVER_INITIALIZED": "1",
            "NEKO_PLUGIN_ZMQ_IPC_ENABLED": "false",
        })
        try:
            asyncio.run(check(args.package.resolve(strict=True), sandbox, host_route=args.host_route))
        finally:
            logging.shutdown()


if __name__ == "__main__":
    main()
