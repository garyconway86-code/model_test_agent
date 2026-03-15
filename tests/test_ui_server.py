"""Tests for the remote-friendly browser UI server."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from model_test_agent.tools.report_paths import report_artifacts
from model_test_agent.ui.server import create_ui_server


class TestUIServer:
    def test_root_page_renders(self) -> None:
        server_info = create_ui_server(port=0, defaults={"target_dir": "/tmp/demo"})
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            content = urlopen(server_info.base_url).read().decode("utf-8")
            assert "Model Debug Agent | 智能体辅助日志分析" in content
            assert "/tmp/demo" in content
            assert "大模型节点" in content
            assert "工具节点" in content
            assert "日志提取" in content
            assert "根因分析" in content
            assert "经验入库" in content
            assert "目录约定" in content
            assert "Converter_result/convert/.log/" in content
            assert "PID" in content
            assert str(os.getpid()) in content
            assert "LLM 健康度" in content
            assert "Embedding / Reranker 不可用时会自动降级，不会阻断主流程" in content
            assert "RAG 会自动退回本地词法检索" in content
            assert "跳过 reranker，保留原始检索结果顺序，主流程仍可继续" in content
            assert 'id="job-log"' in content
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

    def test_run_api_conflict_includes_latest_snapshot(self) -> None:
        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            def _raise(_config):
                raise RuntimeError("A pipeline job is already running")

            server_info.server.RequestHandlerClass._app.runner.start = _raise
            server_info.server.RequestHandlerClass._app.runner.latest = lambda: type(
                "Snapshot",
                (),
                {"to_dict": lambda self: {"job_id": "demo1234", "status": "running", "detail": "debug"}},
            )()
            body = json.dumps({"target_dir": "/tmp/models"}).encode("utf-8")
            request = Request(
                f"{server_info.base_url}/api/run",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                urlopen(request)
                raise AssertionError("Expected HTTP 409")
            except Exception as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert payload["error"] == "A pipeline job is already running"
                assert payload["snapshot"]["status"] == "running"
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_report_lookup_returns_existing_report(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "Models_to_be_tested"
        target_dir.mkdir()
        artifacts = report_artifacts(tmp_path / "output", target_dir)
        artifacts["html"].write_text("<html><body>report</body></html>", encoding="utf-8")
        artifacts["xlsx"].write_text("xlsx", encoding="utf-8")

        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = json.loads(
                urlopen(
                    f"{server_info.base_url}/api/report-lookup?target_dir={target_dir}&output_dir={tmp_path / 'output'}"
                ).read().decode("utf-8")
            )
            assert payload["exists"] is True
            assert payload["status"] == "completed"
            assert payload["detail"] == "Loaded existing report"
            assert payload["report_html_path"].endswith("report.html")
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_llm_health_api_returns_profiles(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.ui.server.check_all_profiles",
            lambda config_path="", timeout=6: [
                {
                    "ok": True,
                    "profile": "default",
                    "kind": "chat",
                    "model": "demo-model",
                    "latency_ms": 12.3,
                    "error": "",
                }
            ],
        )

        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = json.loads(urlopen(f"{server_info.base_url}/api/llm-health").read().decode("utf-8"))
            assert payload["ok"] is True
            assert payload["healthy"] == 1
            assert payload["total"] == 1
            assert payload["profiles"][0]["profile"] == "default"
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_force_rerun_bypasses_existing_report_shortcut(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "Models_to_be_tested"
        target_dir.mkdir()
        artifacts = report_artifacts(tmp_path / "output", target_dir)
        artifacts["html"].write_text("<html><body>report</body></html>", encoding="utf-8")

        server_info = create_ui_server(port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            server_info.server.RequestHandlerClass._app.runner.start = lambda config: type(
                "Snapshot",
                (),
                {
                    "to_dict": lambda self: {
                        "job_id": "force123",
                        "status": "running",
                        "detail": f"force={config.get('target_dir')}",
                    }
                },
            )()
            body = json.dumps(
                {
                    "target_dir": str(target_dir),
                    "output_dir": str(tmp_path / "output"),
                    "force_rerun": True,
                }
            ).encode("utf-8")
            request = Request(
                f"{server_info.base_url}/api/run",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            payload = json.loads(urlopen(request).read().decode("utf-8"))
            assert payload["job_id"] == "force123"
            assert payload["status"] == "running"
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)
