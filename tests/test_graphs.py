"""Tests for graph construction (no LLM calls — structure only)."""

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
from model_test_agent.graphs.main_graph import build_main_graph


class TestGraphConstruction:
    """Verify that all graphs compile without errors."""

    def test_classification_subgraph_compiles(self) -> None:
        graph = build_classification_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_debug_subgraph_compiles(self) -> None:
        graph = build_debug_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_snr_subgraph_compiles(self) -> None:
        graph = build_snr_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_main_graph_compiles(self) -> None:
        graph = build_main_graph(compile=True)
        assert graph is not None

    def test_main_graph_uncompiled(self) -> None:
        graph = build_main_graph(compile=False)
        # Should be a StateGraph, not compiled
        assert hasattr(graph, "compile")
