"""AST-based tests enforcing architectural module boundaries across packages."""

import ast
from pathlib import Path


def check_module_imports(source_code: str, file_rel_path: str) -> list[str]:
    """Parse python code into an AST and return violations of module boundary rules."""
    tree = ast.parse(source_code, filename=file_rel_path)
    violations: list[str] = []

    # Standardize forward slashes
    norm_path = file_rel_path.replace("\\", "/")

    for node in ast.walk(tree):
        imported_modules: list[str] = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.append(node.module)
                for alias in node.names:
                    imported_modules.append(f"{node.module}.{alias.name}")

        for mod in imported_modules:
            # Rule 1: qdrant_client only in stores/vector.py
            if mod == "qdrant_client" or mod.startswith("qdrant_client."):
                if not norm_path.endswith("stores/vector.py"):
                    violations.append(
                        f"{norm_path}: Forbidden import '{mod}'. "
                        "qdrant_client may only be imported in stores/vector.py."
                    )

            # Rule 2: Gemini SDK only in providers/gemini.py
            if mod in ("google.genai", "google.generativeai") or mod.startswith(
                ("google.genai.", "google.generativeai.")
            ):
                if not norm_path.endswith("providers/gemini.py"):
                    violations.append(
                        f"{norm_path}: Forbidden import '{mod}'. "
                        "Gemini SDK may only be imported in providers/gemini.py."
                    )

            # Rule 3: sqlalchemy only in stores/ and stores/repos/
            if mod == "sqlalchemy" or mod.startswith("sqlalchemy."):
                if "/stores/" not in norm_path:
                    violations.append(
                        f"{norm_path}: Forbidden import '{mod}'. "
                        "sqlalchemy may only be imported in stores/ or stores/repos/."
                    )

    return violations


def test_codebase_module_boundaries() -> None:
    """Scan all Python files under src/research_desk to ensure no boundary rules are violated."""
    src_root = Path(__file__).parents[1] / "src" / "research_desk"
    all_violations: list[str] = []

    for py_file in src_root.rglob("*.py"):
        rel_path = str(py_file.relative_to(src_root.parent.parent))
        content = py_file.read_text(encoding="utf-8")
        violations = check_module_imports(content, rel_path)
        all_violations.extend(violations)

    assert not all_violations, "Module boundary violations found:\n" + "\n".join(all_violations)


def test_boundary_checker_flags_forbidden_imports() -> None:
    """Verify that check_module_imports properly flags unauthorized imports in an agent module."""
    mock_agent_code = """
import qdrant_client
from google import genai
import sqlalchemy
"""
    violations = check_module_imports(mock_agent_code, "src/research_desk/agents/collector.py")
    assert len(violations) == 3
    assert any("qdrant_client" in v for v in violations)
    assert any("Gemini SDK" in v for v in violations)
    assert any("sqlalchemy" in v for v in violations)
