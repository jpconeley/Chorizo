"""Batch jobs: `uv run chorizo <command>`."""

import argparse

from chorizo import seed
from chorizo.analytics import service
from chorizo.db import get_sessionmaker
from chorizo.ingest import ctgov


def main() -> None:
    parser = argparse.ArgumentParser(prog="chorizo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-reference", help="Load published stage benchmarks")
    commands.add_parser("seed-demo", help="Load fictional demo assets and users (local only)")
    ingest = commands.add_parser("ingest-ctgov", help="Import trials from ClinicalTrials.gov")
    ingest.add_argument("--query", help="Free-text filter, e.g. a condition or sponsor")
    ingest.add_argument("--max-pages", type=int, help="Stop after N pages of 100 studies")
    commands.add_parser("compute-benchmarks", help="Recompute stage benchmarks from asset histories")
    commands.add_parser("refresh-estimates", help="Recompute per-asset probability of success")
    args = parser.parse_args()

    with get_sessionmaker()() as session:
        match args.command:
            case "seed-reference":
                print(f"benchmarks added: {seed.seed_reference(session)}")
            case "seed-demo":
                seed.seed_demo(session)
                print(f"demo data loaded; demo users use password '{seed.DEMO_PASSWORD}'")
            case "ingest-ctgov":
                print(f"trials upserted: {ctgov.run(session, args.query, args.max_pages)}")
            case "compute-benchmarks":
                print(f"benchmarks written: {service.recompute_benchmarks(session)}")
            case "refresh-estimates":
                print(f"assets estimated: {service.refresh_estimates(session)}")


if __name__ == "__main__":
    main()
