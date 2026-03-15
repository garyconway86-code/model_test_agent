"""Thin browser UI for remote-friendly pipeline execution."""

from model_test_agent.ui.job_runner import PipelineJobRunner
from model_test_agent.ui.server import UIServerInfo, create_ui_server

__all__ = ["PipelineJobRunner", "UIServerInfo", "create_ui_server"]
