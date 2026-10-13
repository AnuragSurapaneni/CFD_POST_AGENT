"""Persistent registry for analyst-authored Python calculations."""

from __future__ import annotations

import importlib.util
import inspect
import json
import textwrap
import types
from pathlib import Path
from typing import Any, Callable

from .models import RequestError

REGISTRY = Path(".cfdpost/functions.json")
_NOTEBOOK_FUNCTIONS: dict[str, Callable[..., Any]] = {}


def register(name: str, source: str, function: str) -> Path:
    if not name.isidentifier():
        raise RequestError("Custom function names must be valid Python identifiers.")
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise RequestError(f"Custom function file does not exist: {path}")
    registry = REGISTRY.resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    values = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else {}
    values[name] = {"source": str(path), "function": function}
    registry.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    return registry


def register_callable(name: str, function: Callable[..., Any]) -> Path:
    """Persist a notebook function; imported modules and simple constants are copied with it."""
    if not callable(function):
        raise RequestError("The notebook value must be callable.")
    try:
        function_source = textwrap.dedent(inspect.getsource(function))
    except (OSError, TypeError) as exc:
        raise RequestError("Could not read this notebook function's source. Put it in a Python file and register that file instead.") from exc
    name = name if name.isidentifier() else ""
    if not name:
        raise RequestError("Custom function names must be valid Python identifiers.")
    header = []
    for global_name in function.__code__.co_names:
        value = function.__globals__.get(global_name)
        if isinstance(value, types.ModuleType):
            header.append(f"import {value.__name__} as {global_name}")
        elif isinstance(value, (bool, int, float, str, tuple, list, dict)):
            header.append(f"{global_name} = {value!r}")
    directory = Path(".cfdpost/notebook_functions")
    directory.mkdir(parents=True, exist_ok=True)
    source_path = (directory / f"{name}.py").resolve()
    source_path.write_text("\n".join(dict.fromkeys(header)) + "\n\n" + function_source, encoding="utf-8")
    _NOTEBOOK_FUNCTIONS[name] = function
    return register(name, str(source_path), function.__name__)


def load(name: str, registry_path: str | None = None) -> Callable[..., Any]:
    if name in _NOTEBOOK_FUNCTIONS:
        return _NOTEBOOK_FUNCTIONS[name]
    registry = Path(registry_path).expanduser().resolve() if registry_path else REGISTRY.resolve()
    if not registry.exists():
        raise RequestError(f"No custom function registry at {registry}; register a Python file first.")
    entries = json.loads(registry.read_text(encoding="utf-8"))
    if name not in entries:
        raise RequestError(f"Custom function {name!r} is not registered. Registered: {sorted(entries)}")
    spec_data = entries[name]
    source = Path(spec_data["source"])
    spec = importlib.util.spec_from_file_location(f"cfdpost_user_{name}", source)
    if spec is None or spec.loader is None:
        raise RequestError(f"Cannot load custom function source {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = getattr(module, spec_data["function"], None)
    if not callable(result):
        raise RequestError(f"{spec_data['function']!r} is not callable in {source}")
    return result


def kolmogorov_scales(nu: float, epsilon: float) -> dict[str, float]:
    """Return eta, tau, and velocity scales for kinematic viscosity and dissipation."""
    if nu <= 0 or epsilon <= 0:
        raise RequestError("Kinematic viscosity and dissipation rate must be positive.")
    return {
        "length_m": (nu**3 / epsilon) ** 0.25,
        "time_s": (nu / epsilon) ** 0.5,
        "velocity_m_s": (nu * epsilon) ** 0.25,
    }
