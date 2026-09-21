import ast
from pathlib import Path

# services/ must stay framework-agnostic: a future CLI or agent interface
# will call the same functions the web layer calls, so no business rule may
# ever depend on Flask or on the web layer.
SERVICES_DIR = Path(__file__).resolve().parent.parent / "src" / "services"


def _imported_modules(tree: ast.Module) -> list[str]:
    """Return every module name imported anywhere in a parsed file."""
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _is_forbidden(module: str) -> bool:
    """A module is forbidden if it is (or is a submodule of) flask or src.web."""
    return module in ("flask", "src.web") or module.startswith(("flask.", "src.web."))


def test_services_never_import_flask_or_web():
    """Walk every file under services/ and fail if any imports flask or src.web."""
    violations = []
    for path in SERVICES_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _imported_modules(tree):
            if _is_forbidden(module):
                violations.append(f"{path}: imports {module}")
    assert not violations, "\n".join(violations)


# The MCP tool layer is transport-agnostic too: only the HTTP endpoint
# (mcp_server/http.py) may know about Flask.
MCP_DIR = Path(__file__).resolve().parent.parent / "src" / "mcp_server"


def test_mcp_tool_layer_never_imports_flask_or_web():
    """Every file under mcp_server/ except http.py must stay free of flask and src.web."""
    violations = []
    for path in MCP_DIR.rglob("*.py"):
        if path.name == "http.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for module in _imported_modules(tree):
            if _is_forbidden(module):
                violations.append(f"{path}: imports {module}")
    assert not violations, "\n".join(violations)
