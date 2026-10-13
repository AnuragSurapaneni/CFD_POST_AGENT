"""Command line interface for reviewing, preparing, and running workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .custom import register
from .models import AnalysisRequest, RequestError
from .workflow import prepare


def _read_request(path: str) -> AnalysisRequest:
    source = Path(path).expanduser().resolve()
    return AnalysisRequest.from_dict(json.loads(source.read_text(encoding="utf-8")))


def _review(request: AnalysisRequest) -> None:
    print(f"Input: {request.input}")
    print(f"Output: {request.output}")
    print(f"Execution: {request.execution}")
    if request.execution == "local":
        print(f"Local CPUs: {request.cpus}")
    else:
        print(f"Slurm nodes: {request.nodes}; CPUs per node: {request.cpus_per_node}")
    print("Ordered actions:")
    for index, action in enumerate(request.actions, 1):
        print(f"  {index}. {action['type']}: {json.dumps(action, sort_keys=True)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cfdpost", description="Plan and run reproducible CFD post-processing jobs")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("prepare", "review a draft, request approval, and generate scripts"),
                            ("execute", "run a previously approved request"),
                            ("run", "review, approve, prepare, and run locally")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("request", help="JSON request file")
    add_custom = commands.add_parser("register-function", help="persist a user function from a Python file")
    add_custom.add_argument("name")
    add_custom.add_argument("source")
    add_custom.add_argument("function")
    args = parser.parse_args(argv)
    try:
        if args.command == "register-function":
            print(register(args.name, args.source, args.function))
            return 0
        request = _read_request(args.request)
        if args.command == "execute":
            from .executor import execute

            print(execute(request, Path(args.request)))
            return 0
        _review(request)
        if request.approved:
            print("Request was already approved.")
        else:
            if not sys.stdin.isatty():
                raise RequestError("Request is not approved. Run prepare interactively or approve it in a notebook.")
            answer = input("Run this exact plan? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Plan not approved; nothing was run.")
                return 1
            request.approved = True
        script = prepare(request)
        print(f"Generated: {script}")
        if args.command == "run":
            if request.execution != "local":
                raise RequestError("Slurm plans generate scripts for you to submit; use prepare instead of run.")
            from .executor import execute

            print(execute(request, Path(args.request)))
        return 0
    except (RequestError, OSError, ValueError, json.JSONDecodeError) as exc:
        request = locals().get("request")
        if request is not None:
            try:
                output = Path(request.output).expanduser()
                output.mkdir(parents=True, exist_ok=True)
                (output / "run-error.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            except OSError:
                pass
        print(f"cfdpost: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        request = locals().get("request")
        if request is not None:
            try:
                output = Path(request.output).expanduser()
                output.mkdir(parents=True, exist_ok=True)
                (output / "run-error.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            except OSError:
                pass
        print(f"cfdpost: execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
