"""Build and run the ``versions-maven-plugin`` goals via Maven."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

GROUP = "org.codehaus.mojo:versions-maven-plugin"

# level -> (allowMajorUpdates, allowMinorUpdates, allowIncrementalUpdates)
_LEVEL_FLAGS = {
    "major": (True, True, True),
    "minor": (False, True, True),
    "bugfix": (False, False, True),
}


@dataclass
class MavenError(RuntimeError):
    returncode: int
    tail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"maven failed (exit {self.returncode})\n{self.tail}"


def allow_flags(level: str):
    try:
        return _LEVEL_FLAGS[level]
    except KeyError:
        raise ValueError(f"invalid level: {level!r} (expected major|minor|bugfix)")


def build_goals(plugin_version: str, want_plugins: bool, want_properties: bool) -> List[str]:
    goals = [f"{GROUP}:{plugin_version}:display-dependency-updates"]
    if want_plugins:
        goals.append(f"{GROUP}:{plugin_version}:display-plugin-updates")
    if want_properties:
        goals.append(f"{GROUP}:{plugin_version}:display-property-updates")
    return goals


def ensure_available(mvn: str = "mvn") -> None:
    if shutil.which(mvn) is None:
        raise FileNotFoundError(
            f"'{mvn}' was not found on PATH. Maven is required to run the update goals."
        )


def run(project_pom: str, goals: List[str], width: int, level: str,
        rules_uri: Optional[str] = None, mvn: str = "mvn",
        tail_lines: int = 25) -> str:
    """Run the goals against ``project_pom`` and return the combined stdout+stderr log text."""
    major, minor, incremental = allow_flags(level)
    cmd = [mvn, "-B", "-ntp", "-f", project_pom, *goals,
           f"-Dversions.outputLineWidth={width}",
           f"-DallowMajorUpdates={str(major).lower()}",
           f"-DallowMinorUpdates={str(minor).lower()}",
           f"-DallowIncrementalUpdates={str(incremental).lower()}",
           "-DprocessDependencyManagement=true",
           # Treat an imported BOM as the updatable unit: report the BOM's own update instead of
           # dissolving it into every artifact it manages (dozens of phantom "unused" entries).
           "-DprocessDependencyManagementTransitive=false"]
    if rules_uri:
        cmd.append(f"-Dmaven.version.rules={rules_uri}")
    return _run(cmd, tail_lines)


def run_tree(project_pom: str, mvn: str = "mvn", tail_lines: int = 25) -> str:
    """Run ``dependency:tree`` against ``project_pom`` and return the combined log text."""
    return _run([mvn, "-B", "-ntp", "-f", project_pom, "dependency:tree"], tail_lines)


def _run(cmd: List[str], tail_lines: int) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = "\n".join(log.splitlines()[-tail_lines:])
        raise MavenError(proc.returncode, tail)
    return log
