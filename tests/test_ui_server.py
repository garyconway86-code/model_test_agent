"""Tests for the remote-friendly browser UI server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from model_test_agent.ui.server import create_ui_server


class TestUIServer:
    def test_root_page_renders(self) -> None:
        server_info = create_ui_server(port=0, defaults={"target_dir": "/tmp/demo"})
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            content = urlopen(server_info.base_url).read().decode("utf-8")
            assert "模型日志分析" in content
            assert "/tmp/demo" in content
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_fs_api_lists_directories(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "c.yaml").write_text("demo: true\n", encoding="utf-8")
        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = json.loads(
                urlopen(f"{server_info.base_url}/api/fs?path={tmp_path}").read().decode("utf-8")
            )
            names = [item["name"] for item in payload["entries"]]
            assert names == ["a", "b"]

            file_payload = json.loads(
                urlopen(f"{server_info.base_url}/api/fs?path={tmp_path}&mode=file").read().decode("utf-8")
            )
            assert any(item["name"] == "c.yaml" and item["kind"] == "file" for item in file_payload["entries"])
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_file_api_reads_and_writes_server_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "target_layout.yaml"
        file_path.write_text("config_patterns:\\n  - demo.yaml\\n", encoding="utf-8")
        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = json.loads(
                urlopen(f"{server_info.base_url}/api/file?path={file_path}").read().decode("utf-8")
            )
            assert payload["name"] == "target_layout.yaml"
            assert "config_patterns" in payload["content"]

            request = Request(
                f"{server_info.base_url}/api/file?path={file_path}",
                data=json.dumps({"content": "config_patterns:\\n  - changed.yaml\\n"}).encode("utf-8"),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            result = json.loads(urlopen(request).read().decode("utf-8"))
            assert result["ok"] is True
            assert "changed.yaml" in file_path.read_text(encoding="utf-8")
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_run_api_uses_runner_and_job_api_returns_snapshot(self) -> None:
        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            server_info.server.RequestHandlerClass._app.runner.start = lambda config: type(
                "Snapshot",
                (),
                {"to_dict": lambda self: {"job_id": "demo1234", "status": "running", "detail": config["target_dir"]}},
            )()
            body = json.dumps({"target_dir": "/tmp/models"}).encode("utf-8")
            request = Request(
                f"{server_info.base_url}/api/run",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            payload = json.loads(urlopen(request).read().decode("utf-8"))
            assert payload["job_id"] == "demo1234"

            server_info.server.RequestHandlerClass._app.runner.latest = lambda: type(
                "Snapshot",
                (),
                {"to_dict": lambda self: {"job_id": "demo1234", "status": "completed", "detail": "done"}},
            )()
            status_payload = json.loads(urlopen(f"{server_info.base_url}/api/job").read().decode("utf-8"))
            assert status_payload["status"] == "completed"
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)
