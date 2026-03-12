"""SNR subgraph — layerwise Signal-to-Noise Ratio analysis.

This subgraph is **completely independent** from the main error-analysis
pipeline.  It can be invoked on its own to compute per-layer SNR metrics
for converted models, which helps diagnose quantization quality issues.

Currently a scaffold — implement ``_compute_snr`` with your actual SNR
computation logic.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from model_test_agent.state import SNRState


def _load_models(state: SNRState) -> dict[str, Any]:
    """Load model metadata needed for SNR computation."""
    # Models are already in state if passed from the main graph.
    # When run standalone, they come from the initial state dict.
    models = state.get("models", [])
    return {"models": models}


def _compute_snr(state: SNRState) -> dict[str, Any]:
    """Compute layerwise SNR for each model.

    TODO: Replace this scaffold with your actual SNR computation.
    Expected output format per model::

        {
            "model_name": {
                "layer_0": {"snr_db": 42.5, "shape": [64, 3, 7, 7]},
                "layer_1": {"snr_db": 38.1, "shape": [64, 64, 3, 3]},
                ...
            }
        }

    The current implementation returns a placeholder to keep the graph
    runnable.
    """
    models = state.get("models", [])
    snr_results: dict[str, Any] = {}
    for model in models:
        snr_results[model.name] = {
            "_placeholder": True,
            "_note": "实现你的 layerwise SNR 计算逻辑",
        }
    return {"snr_results": snr_results}


def _format_results(state: SNRState) -> dict[str, Any]:
    """Post-process SNR results (e.g. flag low-SNR layers)."""
    snr_results = state.get("snr_results", {})
    # Placeholder: future logic to flag layers below a threshold
    return {"snr_results": snr_results}


def build_snr_subgraph() -> StateGraph:
    """Construct and return the SNR analysis subgraph (uncompiled).

    Nodes:
      1. ``load_models``    — prepare model info
      2. ``compute_snr``    — per-layer SNR computation (scaffold)
      3. ``format_results`` — post-process and flag issues

    This graph is fully independent and can be run without the
    classification or debug subgraphs.
    """
    graph = StateGraph(SNRState)

    graph.add_node("load_models", _load_models)
    graph.add_node("compute_snr", _compute_snr)
    graph.add_node("format_results", _format_results)

    graph.set_entry_point("load_models")
    graph.add_edge("load_models", "compute_snr")
    graph.add_edge("compute_snr", "format_results")
    graph.add_edge("format_results", END)

    return graph
