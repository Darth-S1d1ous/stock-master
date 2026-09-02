import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Any
from uuid import UUID

EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 2
EXIT_CONFIGURATION_ERROR = 3
EXIT_RUN_CONFLICT = 4
EXIT_ALL_FAILED = 5


class _ArgumentParser(argparse.ArgumentParser):
    """Convert argparse failures into the documented configuration exit code."""

    def error(self, message: str) -> None:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--provider",
            required=True,
            choices=("alpha_vantage", "finnhub", "yahoo_finance"),
        )
        command.add_argument("--output-size", choices=("compact", "full"), default="compact")
        command.add_argument("--timeout-seconds", type=float, default=45.0)
        command.add_argument("--minimum-interval-seconds", type=float, default=1.0)

    refresh_symbol = subparsers.add_parser(
        "refresh-symbol",
        help="Refresh one stock symbol.",
    )
    refresh_symbol.add_argument("symbol")
    add_common_arguments(refresh_symbol)

    refresh_active = subparsers.add_parser(
        "refresh-active",
        help="Refresh unique symbols from active and challenged theses.",
    )
    add_common_arguments(refresh_active)
    return parser


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _emit(payload: dict[str, Any], *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    print(
        json.dumps(payload, default=_json_default, separators=(",", ":"), sort_keys=True),
        file=stream,
        flush=True,
    )


async def _run(args: argparse.Namespace) -> int:
    from app.services.ingestion_runner import (
        IngestionRunConflictError,
        IngestionRunner,
    )

    runner = IngestionRunner(
        provider=args.provider,
        output_size=args.output_size,
        timeout_seconds=args.timeout_seconds,
        minimum_interval_seconds=args.minimum_interval_seconds,
    )
    try:
        if args.command == "refresh-symbol":
            result = await runner.run_symbol(args.symbol)
        else:
            result = await runner.run_active()
    except IngestionRunConflictError as exc:
        _emit({"code": "ingestion_already_running", "message": str(exc)}, error=True)
        return EXIT_RUN_CONFLICT

    _emit({"event": "ingestion_completed", **asdict(result)})
    if result.failed_count == 0:
        return EXIT_SUCCESS
    if result.succeeded_count == 0:
        return EXIT_ALL_FAILED
    return EXIT_PARTIAL_FAILURE


def main() -> int:
    """Run the non-interactive ingestion command and return a stable exit code."""

    try:
        args = _parser().parse_args()
        if args.timeout_seconds <= 0 or args.minimum_interval_seconds < 0:
            raise ValueError("Timeout must be positive and rate interval cannot be negative.")
        return asyncio.run(_run(args))
    except (ValueError, ImportError):
        _emit(
            {"code": "configuration_error", "message": "Invalid ingestion configuration."},
            error=True,
        )
        return EXIT_CONFIGURATION_ERROR
    except Exception:  # noqa: BLE001  # 顶层入口：将任何未预期异常映射为稳定退出码
        _emit(
            {"code": "ingestion_failed", "message": "The ingestion run could not be started."},
            error=True,
        )
        return EXIT_ALL_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
