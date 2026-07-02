"""Parse ``mvn dependency:tree`` output to classify dependencies as direct or transitive.

The tree goal prints, per reactor module, an indented tree such as::

    [INFO] --- maven-dependency-plugin:3.7.0:tree (default-cli) @ module-b ---
    [INFO] com.example.demo:module-b:jar:1.0.0-SNAPSHOT
    [INFO] +- junit:junit:jar:4.12:test
    [INFO] |  \\- org.hamcrest:hamcrest-core:jar:1.3:test
    [INFO] \\- commons-io:commons-io:jar:2.6:compile

Depth 1 entries are the module's *direct* dependencies; anything deeper is *transitive* and is
attributed to its depth-1 ancestor (the "root" dependency that pulls it in).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Set

# Reactor header of the tree goal, e.g.:
#   --- maven-dependency-plugin:3.7.0:tree (default-cli) @ module-b ---
TREE_HEADER_RE = re.compile(r"---\s+\S+:tree\s+\([^)]*\)\s+@\s+(\S+)\s+---")
INFO_RE = re.compile(r"^\[INFO\]\s?")
# A tree node: ancestor levels are 3-char units ('|  ' or '   '), then '+- ' or '\- ', then the
# coordinate 'groupId:artifactId:type[:classifier]:version[:scope]'.
NODE_RE = re.compile(r"^((?:\|  |   )*)[+\\]- (\S+)")


@dataclass
class Origin:
    """How a groupId:artifactId enters the dependency tree."""
    direct: bool = False
    roots: Set[str] = field(default_factory=set)  # depth-1 ancestors when transitive


def parse_tree_text(text: str) -> Dict[str, Dict[str, Origin]]:
    """Parse captured ``dependency:tree`` output into ``{module: {ga: Origin}}``."""
    per_module: Dict[str, Dict[str, Origin]] = {}
    module = None
    stack: Dict[int, str] = {}  # depth -> ga of the node last seen at that depth

    for raw in text.splitlines():
        hdr = TREE_HEADER_RE.search(raw)
        if hdr:
            module = hdr.group(1)
            per_module.setdefault(module, {})
            stack = {}
            continue
        if module is None:
            continue
        m = NODE_RE.match(INFO_RE.sub("", raw))
        if not m:
            continue
        parts = m.group(2).split(":")
        if len(parts) < 4:  # need at least group:artifact:type:version
            continue
        depth = len(m.group(1)) // 3 + 1
        ga = f"{parts[0]}:{parts[1]}"
        stack[depth] = ga
        origin = per_module[module].setdefault(ga, Origin())
        if depth == 1:
            origin.direct = True
        else:
            origin.roots.add(stack[1])
    return per_module


def merge_origins(per_module: Dict[str, Dict[str, Origin]]) -> Dict[str, Origin]:
    """Merge per-module origins into one project-wide map (direct anywhere wins)."""
    merged: Dict[str, Origin] = {}
    for origins in per_module.values():
        for ga, origin in origins.items():
            g = merged.setdefault(ga, Origin())
            g.direct = g.direct or origin.direct
            g.roots |= origin.roots
    return merged


def origin_label(ga: str, origins: Dict[str, Origin]) -> str:
    """Human-readable origin for a dependency row: 'direct', 'via <root>', or a managed note."""
    origin = origins.get(ga)
    if origin is None:
        # reported (e.g. from dependencyManagement) but absent from every module's tree
        return "managed, unused"
    if origin.direct:
        return "direct"
    return "via " + ", ".join(sorted(origin.roots))
