"""Command-line entry point for RuleGarden."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Create the stable top-level parser shared by future subcommands."""
    return argparse.ArgumentParser(
        prog="rulegarden",
        description="Manage project-level Codex rules.",
    )


def main() -> int:
    """Run the CLI and return an OS-compatible success status."""
    build_parser().parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
