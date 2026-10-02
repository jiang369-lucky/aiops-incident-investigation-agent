from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from .application import create_application
from .evaluation import evaluate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="incident-agent",
        description="Evidence-grounded OpenStack incident investigation agent",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="Build the PostgreSQL log index")
    prepare.add_argument("--force", action="store_true", help="Rebuild an existing index")

    investigate = commands.add_parser("investigate", help="Investigate one VM instance")
    investigate.add_argument("instance_id")
    investigate.add_argument("--mode", choices=["heuristic", "llm"], default=None)
    investigate.add_argument(
        "--approve-ticket",
        action="store_true",
        help="After displaying the report, persist an approved draft in PostgreSQL",
    )

    evaluation = commands.add_parser("evaluate", help="Run the locked-label smoke evaluation")
    evaluation.add_argument("--mode", choices=["heuristic", "llm"], default="heuristic")
    evaluation.add_argument(
        "--negative-count",
        type=int,
        default=50,
        help="Number of held-out normal2 instances (default: 50)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    application = create_application()
    if args.command == "prepare":
        counts = application.store.build(application.settings.raw_data_path, force=bool(args.force))
        print(json.dumps({"database": "PostgreSQL", "counts": counts}, indent=2))
        return 0

    if args.command == "investigate":
        task = (
            f"Investigate OpenStack instance {args.instance_id}. "
            "Produce an evidence-grounded report and do not take remediation action."
        )
        result = await application.harness(args.mode).run(task)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        if args.approve_ticket and result.report:
            saved = application.tools.save_ticket_draft(
                ticket=result.report.to_dict(), approved=True
            )
            print(json.dumps({"ticket": saved}, ensure_ascii=False, indent=2))
        return 0 if result.status == "completed" else 1

    if args.command == "evaluate":
        report = await evaluate(
            application,
            mode=args.mode,
            negative_count=max(1, min(args.negative_count, 1_000)),
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    return 2


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(_run(_parser().parse_args(argv))))


if __name__ == "__main__":
    main()
