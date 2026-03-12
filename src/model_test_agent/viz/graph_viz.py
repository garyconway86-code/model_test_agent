"""Graph structure visualization utilities.

Provides two ways to visualize graph topology without LangGraph Studio:
  1. Mermaid diagram (text-based, renders in any Markdown viewer)
  2. PNG export via ``draw_mermaid_png()`` (if dependencies available)

These work offline — no LangGraph Platform or Docker required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_mermaid(graph: Any, output_path: str | None = None) -> str:
    """Export the graph structure as a Mermaid diagram string.

    Parameters
    ----------
    graph : CompiledGraph
        A compiled LangGraph graph.
    output_path : str | None
        If set, also writes the diagram to a ``.md`` file.

    Returns
    -------
    str
        The Mermaid diagram source.
    """
    try:
        mermaid_str = graph.get_graph().draw_mermaid()
    except Exception:
        mermaid_str = _fallback_mermaid(graph)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# Graph Structure\n\n```mermaid\n{mermaid_str}\n```\n"
        path.write_text(content, encoding="utf-8")

    return mermaid_str


def export_png(graph: Any, output_path: str = "graph.png") -> Path | None:
    """Export graph as a PNG image.

    Uses LangGraph's built-in ``draw_mermaid_png()`` which requires
    the ``pyppeteer`` or ``playwright`` package.  Returns *None* if
    the export fails (missing dependencies).
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
        path.write_bytes(png_bytes)
        return path
    except Exception:
        return None


def print_graph_ascii(graph: Any) -> str:
    """Print a simple ASCII representation of graph nodes and edges.

    Always works — no optional dependencies needed.
    """
    try:
        g = graph.get_graph()
        nodes = list(g.nodes)
        edges = list(g.edges)
    except Exception:
        return "(无法获取图结构)"

    lines = ["节点 (Nodes):"]
    for node in nodes:
        lines.append(f"  [{node}]")

    lines.append("\n边 (Edges):")
    for edge in edges:
        src = edge[0] if isinstance(edge, tuple) else getattr(edge, "source", "?")
        dst = edge[1] if isinstance(edge, tuple) else getattr(edge, "target", "?")
        lines.append(f"  {src} ──▶ {dst}")

    return "\n".join(lines)


def _fallback_mermaid(graph: Any) -> str:
    """Build a basic mermaid diagram from graph metadata."""
    try:
        g = graph.get_graph()
        lines = ["graph TD"]
        for edge in g.edges:
            src = edge[0] if isinstance(edge, tuple) else getattr(edge, "source", "?")
            dst = edge[1] if isinstance(edge, tuple) else getattr(edge, "target", "?")
            lines.append(f"    {src} --> {dst}")
        return "\n".join(lines)
    except Exception:
        return "graph TD\n    A[Error: cannot introspect graph]"
