"""Tests for the lightweight shared-review report server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from model_test_agent.tools.report_server import create_report_server, review_state_path


class TestReportServer:
    def test_review_state_path_uses_report_stem(self, tmp_path: Path) -> None:
        report_path = tmp_path / "demo_report.html"

        assert review_state_path(report_path) == tmp_path / "demo_report.review.json"

    def test_server_reads_and_writes_shared_review_state(self, tmp_path: Path) -> None:
        report_path = tmp_path / "demo_report.html"
        report_path.write_text("<html><body>demo</body></html>", encoding="utf-8")

        server_info = create_report_server(report_path, port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            get_response = urlopen(f"{server_info.base_url}/api/review-state?report=%2Fdemo_report.html")
            get_payload = json.loads(get_response.read().decode("utf-8"))
            assert get_payload["rows"] == {}

            body = json.dumps({
                "rows": {
                    "row-1|m1|/tmp/a.log|10|shape_mismatch": {
                        "checkedBy": "alice",
                        "comment": "need compiler owner review",
                    }
                }
            }).encode("utf-8")
            request = Request(
                f"{server_info.base_url}/api/review-state?report=%2Fdemo_report.html",
                data=body,
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            put_response = urlopen(request)
            put_payload = json.loads(put_response.read().decode("utf-8"))
            assert put_payload["ok"] is True

            saved = json.loads(review_state_path(report_path).read_text(encoding="utf-8"))
            assert saved["row-1|m1|/tmp/a.log|10|shape_mismatch"]["checkedBy"] == "alice"
            assert saved["row-1|m1|/tmp/a.log|10|shape_mismatch"]["updatedAt"]
            assert saved["row-1|m1|/tmp/a.log|10|shape_mismatch"]["history"]

            refreshed = json.loads(
                urlopen(f"{server_info.base_url}/api/review-state?report=%2Fdemo_report.html").read().decode("utf-8")
            )
            assert refreshed["rows"]["row-1|m1|/tmp/a.log|10|shape_mismatch"]["comment"] == "need compiler owner review"

            second_request = Request(
                f"{server_info.base_url}/api/review-state?report=%2Fdemo_report.html",
                data=json.dumps({
                    "rows": {
                        "row-1|m1|/tmp/a.log|10|shape_mismatch": {
                            "checkedBy": "alice",
                            "comment": "resolved with new calibration data",
                        }
                    }
                }).encode("utf-8"),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            urlopen(second_request)
            saved_again = json.loads(review_state_path(report_path).read_text(encoding="utf-8"))
            assert len(saved_again["row-1|m1|/tmp/a.log|10|shape_mismatch"]["history"]) >= 2
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)

    def test_server_rejects_reports_outside_served_directory(self, tmp_path: Path) -> None:
        report_path = tmp_path / "demo_report.html"
        report_path.write_text("<html></html>", encoding="utf-8")
        outside_report = tmp_path.parent / "outside.html"
        outside_report.write_text("<html></html>", encoding="utf-8")

        server_info = create_report_server(report_path, port=0)
        thread = threading.Thread(target=server_info.server.serve_forever, daemon=True)
        thread.start()
        try:
            try:
                urlopen(f"{server_info.base_url}/api/review-state?report=..%2Foutside.html")
            except HTTPError as exc:
                payload = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 403
                assert "outside the served directory" in payload["error"]
            else:
                raise AssertionError("Expected a 403 response for escaped report paths")
        finally:
            server_info.server.shutdown()
            server_info.server.server_close()
            thread.join(timeout=2)
