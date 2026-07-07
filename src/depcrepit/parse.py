"""Parse captured ``versions-maven-plugin`` output into structured update records."""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import xml.etree.ElementTree as ET

# Reactor header, e.g.:
#   --- versions-maven-plugin:2.18.0:display-dependency-updates (default-cli) @ module-a ---
HEADER_RE = re.compile(r"---\s+\S*?(display-\S+-updates)\s+\([^)]*\)\s+@\s+(\S+)\s+---")
DEPMGMT_RE = re.compile(r"in Dependency Management have newer versions", re.I)
DEPS_RE = re.compile(r"in Dependencies have newer versions", re.I)
INFO_RE = re.compile(r"^\[INFO\]\s?")
ENTRY_RE = re.compile(r"^(.*?)\s+->\s+(\S+)\s*$")  # NAME ...... OLD -> NEW
VERSION_TOKEN = re.compile(r"^[\w.\-+${}]+$")
# A dependency/plugin/property name token (coordinates contain ':', properties use '${}').
NAME_TOKEN = re.compile(r"^[\w.\-+${}:]+$")

POM_NS = "{http://maven.apache.org/POM/4.0.0}"


@dataclass(frozen=True)
class Update:
    scope: str   # 'depmgmt' | 'deps' | 'plugin' | 'property'
    module: str
    name: str
    old: str
    new: str


# --------------------------------------------------------------------------- project model
def scan_project(project_dir: str) -> Tuple[List[str], Set[str], Set[str]]:
    """Return ``(parent_artifacts, managed_dep_ga, bom_ga)`` by reading the project's poms.

    ``bom_ga`` holds the ``dependencyManagement`` entries imported as BOMs
    (``<type>pom</type><scope>import</scope>``); those never appear in ``dependency:tree``.
    """
    parent_artifacts: List[str] = []
    managed: Set[str] = set()
    boms: Set[str] = set()
    for pom in glob.glob(os.path.join(project_dir, "**", "pom.xml"), recursive=True):
        try:
            root = ET.parse(pom).getroot()
        except ET.ParseError:
            continue
        artifact = _text(root.find(f"{POM_NS}artifactId"))
        packaging = _text(root.find(f"{POM_NS}packaging")) or "jar"
        if packaging == "pom" and artifact:
            parent_artifacts.append(artifact)
        for dep in root.findall(
                f"{POM_NS}dependencyManagement/{POM_NS}dependencies/{POM_NS}dependency"):
            g = _text(dep.find(f"{POM_NS}groupId"))
            a = _text(dep.find(f"{POM_NS}artifactId"))
            if g and a:
                managed.add(f"{g}:{a}")
                if (_text(dep.find(f"{POM_NS}scope")) == "import"
                        and _text(dep.find(f"{POM_NS}type")) == "pom"):
                    boms.add(f"{g}:{a}")
    return parent_artifacts, managed, boms


def _text(node) -> str:
    return node.text.strip() if node is not None and node.text else ""


def scan_properties(project_dir: str) -> Dict[str, str]:
    """Return the merged ``<properties>`` of all pom.xml files in the project.

    Used to resolve ``${...}`` version placeholders: with the raw-model dependencyManagement
    processing, the plugin reports a BOM whose version is a property as e.g.
    ``${wildfly.version} -> 26.1.3.Final``, which cannot be compared against the proposal.
    """
    props: Dict[str, str] = {}
    for pom in glob.glob(os.path.join(project_dir, "**", "pom.xml"), recursive=True):
        try:
            root = ET.parse(pom).getroot()
        except ET.ParseError:
            continue
        for node in root.findall(f"{POM_NS}properties/*"):
            name = node.tag.replace(POM_NS, "")
            if node.text and node.text.strip():
                props[name] = node.text.strip()
    return props


_PROP_RE = re.compile(r"\$\{([^}]+)\}")


def resolve_versions(records: List[Update], props: Dict[str, str]) -> List[Update]:
    """Substitute known ``${property}`` placeholders in record versions.

    After resolution a no-op row like ``${wildfly.version} -> 26.1.3.Final`` (where the property
    already holds ``26.1.3.Final``) becomes comparable and is dropped by the upgrade filter.
    Unknown properties are left untouched.
    """
    def resolve(version: str) -> str:
        for _ in range(10):  # allow properties referencing properties, guard against cycles
            m = _PROP_RE.search(version)
            if not m or m.group(1) not in props:
                return version
            version = version[:m.start()] + props[m.group(1)] + version[m.end():]
        return version

    out: List[Update] = []
    for r in records:
        old, new = resolve(r.old), resolve(r.new)
        out.append(r if old == r.old and new == r.new
                   else Update(r.scope, r.module, r.name, old, new))
    return out


# --------------------------------------------------------------------------- log parsing
def parse_log_text(text: str) -> List[Update]:
    """Parse captured Maven output text into a list of :class:`Update`."""
    records: List[Update] = []
    module = "(root)"
    goal = None
    subsection = None     # 'depmgmt' | 'deps' | None (only meaningful for the dependency goal)
    pending_name = None   # name of a wrapped entry awaiting its '-> new' continuation

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        hdr = HEADER_RE.search(line)
        if hdr:
            goal, module = hdr.group(1), hdr.group(2)
            subsection = None
            pending_name = None
            continue

        content = INFO_RE.sub("", line)
        if DEPMGMT_RE.search(content):
            subsection, pending_name = "depmgmt", None
            continue
        if DEPS_RE.search(content):
            subsection, pending_name = "deps", None
            continue

        scope = _scope_for(goal, subsection)
        if scope is None:
            continue

        entry = content.strip().strip(".").strip()
        if not entry:
            continue

        m = ENTRY_RE.match(entry)
        if m:
            left = m.group(1).strip().strip(".").strip()
            new = m.group(2)
            parts = left.split()
            if pending_name is not None:
                # continuation line of a wrapped entry: '<leader> OLD -> NEW'
                name, old = pending_name, (parts[-1] if parts else "")
            elif len(parts) >= 2:
                # single-line entry: 'NAME <leader> OLD -> NEW'
                name, old = parts[0], parts[-1]
            else:
                pending_name = None
                continue
            pending_name = None
            if _valid(name, old, new):
                records.append(Update(scope, module, name, old, new))
        else:
            # possibly the first (name-only) line of a wrapped entry
            tok = entry.split()
            if len(tok) == 1 and NAME_TOKEN.match(tok[0]) and not _looks_like_version(tok[0]):
                pending_name = tok[0]
    return records


def parse_log_file(path: str) -> List[Update]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_log_text(fh.read())


def _scope_for(goal, subsection):
    if goal == "display-dependency-updates":
        return subsection  # 'depmgmt' | 'deps' | None (outside a section)
    if goal == "display-plugin-updates":
        return "plugin"
    if goal == "display-property-updates":
        return "property"
    return None


def _looks_like_version(tok: str) -> bool:
    return bool(re.match(r"^[0-9]", tok))


def _valid(name: str, old: str, new: str) -> bool:
    return bool(name) and bool(old) and bool(new) and "->" not in (old + new) \
        and VERSION_TOKEN.match(new) is not None


def required_width(records: List[Update]) -> int:
    """Widest natural single-line rendering, used to detect plugin-side wrapping."""
    width = 0
    for r in records:
        # indent(4) + name + space + old + " -> " + new + a few leader dots
        width = max(width, 4 + len(r.name) + 1 + len(r.old) + 4 + len(r.new) + 4)
    return width
