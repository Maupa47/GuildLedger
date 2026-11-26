"""The three parts stay apart (docs/dev/archive/PLAN_COMMUNITY.md 3): collection/ never imports from community/."""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "guildledger_bot"


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Import):
            out += [a.name for a in node.names]
    return out


def test_collection_never_imports_community():
    files = sorted((PKG / "collection").glob("*.py"))
    assert files, "collection/ exists"
    bad = [(f.name, m) for f in files for m in imports(f) if "community" in m]
    assert not bad, f"collection/ must not use community/: {bad}"


def test_every_package_folder_is_installed():
    """pyproject uses package discovery, so a new sub-package is installed on the server too."""
    text = (PKG.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["guildledger_bot*"]' in text
    for d in PKG.iterdir():
        if d.is_dir() and d.name != "__pycache__":
            assert (d / "__init__.py").is_file(), f"{d.name}/ needs an __init__.py to be found"
