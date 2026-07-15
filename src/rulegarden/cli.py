"""Command-line entry point for RuleGarden."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rulegarden.app import ApplicationError, RuleGardenApplication
from rulegarden.models import RuleScope
from rulegarden.transactions.service import TransactionError


def build_parser() -> argparse.ArgumentParser:
    """Create the stable top-level parser shared by future subcommands."""
    return argparse.ArgumentParser(
        prog="rulegarden",
        description="Manage project-level Codex rules.",
    )


def _add_project_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=Path.cwd())


def _build_command_parser() -> argparse.ArgumentParser:
    parser = build_parser()
    commands = parser.add_subparsers(dest="command")

    initialize = commands.add_parser("initialize")
    _add_project_root_argument(initialize)

    begin_task = commands.add_parser("begin-task")
    begin_task.add_argument("--summary", required=True)
    begin_task.add_argument("--task-type", action="append", default=[])
    begin_task.add_argument("--path", action="append", default=[])
    begin_task.add_argument("--risk", action="append", default=[])
    _add_project_root_argument(begin_task)

    correction = commands.add_parser("record-correction")
    correction.add_argument("task_id")
    correction.add_argument("instruction")
    correction.add_argument("--summary", required=True)
    correction.add_argument("--path", action="append", default=[])
    correction.add_argument("--task-type", action="append", default=[])
    correction.add_argument("--severity", default="normal")
    _add_project_root_argument(correction)

    finish_task = commands.add_parser("finish-task")
    finish_task.add_argument("task_id")
    _add_project_root_argument(finish_task)

    list_rules = commands.add_parser("list")
    list_rules.add_argument("--status")
    _add_project_root_argument(list_rules)

    transition = commands.add_parser("transition")
    transition.add_argument("rule_id")
    transition.add_argument("target_status")
    _add_project_root_argument(transition)

    undo = commands.add_parser("undo")
    undo.add_argument("transaction_id", nargs="?")
    _add_project_root_argument(undo)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run an explicit lifecycle command and print one machine-readable result."""
    parser = _build_command_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    app = RuleGardenApplication(args.project_root)
    try:
        if args.command == "initialize":
            result = app.initialize()
        elif args.command == "begin-task":
            result = app.begin_task(args.summary, args.task_type, args.path, args.risk)
        elif args.command == "record-correction":
            result = app.record_correction(
                args.task_id,
                args.instruction,
                RuleScope(paths=args.path, task_types=args.task_type),
                args.summary,
                args.path,
                args.severity,
            )
        elif args.command == "finish-task":
            result = app.finish_task(args.task_id)
        elif args.command == "list":
            result = app.list_rules(args.status)
        elif args.command == "transition":
            result = app.transition_rule(args.rule_id, args.target_status)
        elif args.command == "undo":
            result = app.undo(args.transaction_id)
        else:  # argparse keeps this defensive branch unreachable.
            raise ApplicationError(f"unsupported command '{args.command}'")
    except (ApplicationError, TransactionError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
