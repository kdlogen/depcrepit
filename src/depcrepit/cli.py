"""Command-line entry point: report available Maven updates for a multi-module project."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

from . import __version__
from .dependabot import ruleset_xml, rules_from_file
from .deptree import parse_tree_text
from .ignores import STABLE_ONLY_PATTERNS, VENDOR_FORK_PATTERNS, as_ignores
from .maven import MavenError, build_goals, ensure_available, run, run_tree
from .parse import parse_log_text, required_width
from .report import enforce_level, write_reports

MIN_WIDTH = 120


def _progress(msg: str) -> None:
    print(f">>> {msg}", file=sys.stderr)


def _modules_path(output: str) -> str:
    base, ext = os.path.splitext(output)
    return f"{base}-modules{ext}" if ext else f"{output}-modules"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="depcrepit",
        description="Report available dependency / plugin / property updates for a "
                    "multi-module Maven project, as two de-duplicated text files.",
    )
    p.add_argument("-o", "--output", default="maven-updates.txt",
                   help="base output path (default: %(default)s); derives <base>-modules.txt")
    p.add_argument("-p", "--project", default=".",
                   help="Maven project root (default: current directory)")
    p.add_argument("-l", "--level", default="major", choices=["major", "minor", "bugfix"],
                   help="allowed bump level (default: %(default)s)")
    p.add_argument("-d", "--dependabot", metavar="FILE",
                   help="dependabot.yml to convert into a versions ruleset")
    p.add_argument("--allow-prereleases", action="store_true",
                   help="include non-stable versions (alpha/beta/milestone/rc/snapshot/preview/...); "
                        "by DEFAULT these are ignored so the latest STABLE version is reported "
                        "(GA markers like .Final/.RELEASE and build metadata like -jre are kept)")
    p.add_argument("--stable-only", action="store_true", help=argparse.SUPPRESS)  # now the default
    p.add_argument("--allow-vendor-forks", action="store_true",
                   help="include third-party redistribution forks (e.g. -atlassian-1, -redhat-00001); "
                        "by DEFAULT these are ignored in favour of the canonical upstream release")
    p.add_argument("--ignore-version", metavar="REGEX", action="append", default=[],
                   help="full-match regex of versions to ignore (repeatable); e.g. for vendor "
                        r"forks: --ignore-version '(?i).*atlassian.*'")
    p.add_argument("-w", "--line-width", type=int, default=MIN_WIDTH,
                   help=f"output line width; clamped to a minimum of {MIN_WIDTH}")
    p.add_argument("--no-plugins", action="store_true", help="skip plugin updates")
    p.add_argument("--no-properties", action="store_true", help="skip property updates")
    p.add_argument("--no-origins", action="store_true",
                   help="skip the extra dependency:tree run that annotates each dependency "
                        "as [direct] or [via <root dependency>] (transitive)")
    p.add_argument("--plugin-version", default="2.18.0",
                   help="versions-maven-plugin version (default: %(default)s)")
    p.add_argument("--mvn", default="mvn", help="path to the mvn executable (default: mvn)")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    project = os.path.abspath(args.project)
    pom = os.path.join(project, "pom.xml")
    if not os.path.isfile(pom):
        print(f"error: no pom.xml in project root: {project}", file=sys.stderr)
        return 2
    try:
        ensure_available(args.mvn)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    width = max(MIN_WIDTH, args.line_width)
    output = os.path.abspath(args.output)
    modules_out = _modules_path(output)
    goals = build_goals(args.plugin_version, not args.no_plugins, not args.no_properties)

    with tempfile.TemporaryDirectory(prefix="depcrepit.") as work:
        rules_uri = None
        rules, global_ignores = [], []
        if args.dependabot:
            if not os.path.isfile(args.dependabot):
                print(f"error: dependabot file not found: {args.dependabot}", file=sys.stderr)
                return 2
            _progress("converting dependabot config -> versions ruleset")
            r, g = rules_from_file(args.dependabot)
            rules += r
            global_ignores += g
        if not args.allow_prereleases:  # stable-only is the default
            global_ignores += as_ignores(STABLE_ONLY_PATTERNS)
        if not args.allow_vendor_forks:  # vendor forks ignored by default
            global_ignores += as_ignores(VENDOR_FORK_PATTERNS)
        if args.ignore_version:
            global_ignores += as_ignores(args.ignore_version)

        if rules or global_ignores:
            if not args.dependabot:
                _progress("applying version ignore rules")
            ruleset = os.path.join(work, "ruleset.xml")
            with open(ruleset, "w", encoding="utf-8") as fh:
                fh.write(ruleset_xml(rules, global_ignores))
            rules_uri = f"file://{ruleset}"

        try:
            _progress(f"running versions-maven-plugin (level={args.level}, width={width})")
            log = run(pom, goals, width, args.level, rules_uri, mvn=args.mvn)

            _progress("parsing results")
            records = parse_log_text(log)

            need = required_width(records)
            if need > width:
                _progress(f"some entries exceed width {width}; re-running at {need}")
                width = need
                log = run(pom, goals, width, args.level, rules_uri, mvn=args.mvn)
                records = parse_log_text(log)
        except MavenError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    origins = None
    if not args.no_origins:
        try:
            _progress("running dependency:tree (direct/transitive classification)")
            origins = parse_tree_text(run_tree(pom, mvn=args.mvn))
        except MavenError as exc:
            # non-fatal: the report is still useful without origin annotations
            _progress(f"warning: dependency:tree failed (exit {exc.returncode}); "
                      "origin annotations skipped")

    # display-plugin-updates ignores allowMajorUpdates, so enforce --level on plugins ourselves
    records = enforce_level(records, args.level)
    count = write_reports(records, project, output, modules_out, args.level, origins)
    _progress(f"done: {count} distinct updates")
    _progress(f"wrote: {output}")
    _progress(f"wrote: {modules_out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
