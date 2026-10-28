"""Batch jobs: `uv run chorizo <command>`."""

import argparse
import sys
import time

import httpx

from chorizo import seed
from chorizo.analytics import service
from chorizo.db import get_sessionmaker
from chorizo.ingest import ctgov, programs


def _progress(started: float):
    def report(seen: int, imported: int) -> None:
        minutes = (time.monotonic() - started) / 60
        print(f"  {seen:,} studies read, {imported:,} drug trials saved ({minutes:.1f} min)", flush=True)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="chorizo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-reference", help="Load published stage benchmarks")
    commands.add_parser("seed-demo", help="Load fictional demo assets and users (local only)")
    for name, help_text in [
        ("ingest-ctgov", "Import trials from ClinicalTrials.gov"),
        ("refresh-data", "Import trials, build programs, recompute benchmarks and estimates"),
    ]:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--query", help="Free-text filter, e.g. a condition or sponsor")
        sub.add_argument(
            "--max-pages", type=int, help="Stop after N pages of 1,000 studies (for a quick test)"
        )
    commands.add_parser("build-programs", help="Group imported trials into drug programs")
    commands.add_parser("compute-benchmarks", help="Recompute stage benchmarks from drug programs")
    commands.add_parser("refresh-estimates", help="Recompute per-asset probability of success")
    args = parser.parse_args()
    try:
        run(args)
    except httpx.HTTPError as exc:
        sys.exit(f"Could not reach ClinicalTrials.gov ({exc}). Check your internet connection and try again.")


def run(args: argparse.Namespace) -> None:
    with get_sessionmaker()() as session:
        match args.command:
            case "seed-reference":
                print(f"benchmarks added: {seed.seed_reference(session)}")
            case "seed-demo":
                seed.seed_demo(session)
                print(f"demo data loaded; demo users use password '{seed.DEMO_PASSWORD}'")
            case "ingest-ctgov":
                count = ctgov.run(session, args.query, args.max_pages, _progress(time.monotonic()))
                print(f"trials saved: {count:,}")
            case "build-programs":
                print(f"programs: {programs.run(session):,}")
            case "compute-benchmarks":
                print(f"benchmarks written: {service.recompute_benchmarks(session)}")
            case "refresh-estimates":
                print(f"assets estimated: {service.refresh_estimates(session):,}")
            case "refresh-data":
                started = time.monotonic()
                print("1/4 Importing trials from ClinicalTrials.gov (the full import takes a while)...")
                ctgov.run(session, args.query, args.max_pages, _progress(started))
                print("2/4 Building drug programs...")
                print(f"  {programs.run(session):,} programs")
                print("3/4 Computing stage benchmarks...")
                print(f"  {service.recompute_benchmarks(session)} benchmark rows")
                print("4/4 Estimating probability of success...")
                print(f"  {service.refresh_estimates(session):,} assets estimated")
                print(f"Done in {(time.monotonic() - started) / 60:.1f} min.")


if __name__ == "__main__":
    main()
