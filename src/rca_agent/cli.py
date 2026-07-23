from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import QualityGateError, analyze, finalize, prepare, report_bug, validate_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rca-agent",
        description="RCA auditável por clusters para CSV, XLSX e JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Preparar análise e template semântico.")
    prepare_parser.add_argument("input")
    prepare_parser.add_argument("--output", required=True)

    analyze_parser = sub.add_parser("analyze", help="Executar baseline offline completa.")
    analyze_parser.add_argument("input")
    analyze_parser.add_argument("--output", required=True)
    analyze_parser.add_argument("--mode", choices=["rules"], default="rules")

    finalize_parser = sub.add_parser("finalize", help="Finalizar com review opcional.")
    finalize_parser.add_argument("--work", required=True)
    finalize_parser.add_argument("--review")
    finalize_parser.add_argument("--output", required=True)

    validate_parser = sub.add_parser("validate", help="Validar HTML e CSV finais.")
    validate_parser.add_argument("report")

    report_parser = sub.add_parser("report-bug", help="Analisar um bug em JSON.")
    report_parser.add_argument("--input", required=True)
    report_parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.input, args.output)
        elif args.command == "analyze":
            result = analyze(args.input, args.output)
        elif args.command == "finalize":
            result = finalize(args.work, args.output, args.review)
        elif args.command == "validate":
            result = validate_report(args.report)
        elif args.command == "report-bug":
            result = report_bug(args.input, args.output)
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, FileNotFoundError, QualityGateError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

