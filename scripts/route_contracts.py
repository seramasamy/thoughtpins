"""Static FastAPI route discovery for release-policy checks."""

from __future__ import annotations

import ast
from pathlib import Path

HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put"}


class RouteDiscoveryError(RuntimeError):
    """Raised when the authored API route graph cannot be inspected."""


def discover_api_routes(root: Path) -> set[tuple[str, str]]:
    """Collect literal HTTP method/path decorators without importing the app."""

    source_root = root / "src" / "thoughtpins"
    candidates = [source_root / "api.py", *(source_root / "api_routes").glob("*.py")]
    routes: set[tuple[str, str]] = set()
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        raise RouteDiscoveryError(f"no API route modules found under {source_root}")

    for path in existing:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise RouteDiscoveryError(f"cannot inspect {path.relative_to(root)}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue
                function = decorator.func
                if not isinstance(function, ast.Attribute) or function.attr not in HTTP_METHODS:
                    continue
                route_path = decorator.args[0]
                if isinstance(route_path, ast.Constant) and isinstance(route_path.value, str):
                    routes.add((function.attr.upper(), route_path.value))
    return routes


def has_api_route(root: Path, method: str, path: str) -> bool:
    return (method.upper(), path) in discover_api_routes(root)
