from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent


def _read_requirements(filename: str) -> list[str]:
    lines = []
    for raw in (ROOT / filename).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        lines.append(line)
    return lines


setup(
    name="model-test-agent",
    version="0.1.0",
    description="LangGraph-based agent for automated model conversion test analysis",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=_read_requirements("requirements.txt"),
    extras_require={
        "dev": _read_requirements("requirements-dev.txt"),
    },
    entry_points={
        "console_scripts": [
            "model-test-agent=model_test_agent.__main__:main",
        ],
    },
)
