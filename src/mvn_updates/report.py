"""Render the two report files from parsed update records."""
from __future__ import annotations

import datetime
import os
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .deptree import Origin, merge_origins, origin_label
from .parse import Update
from .version import compare, is_upgrade, within_level

Row = Tuple[str, str, str]        # (name, old, new)
Origins = Dict[str, Origin]       # ga -> Origin
ModuleOrigins = Dict[str, Origins]  # module -> ga -> Origin


def enforce_level(records: Iterable[Update], level: str) -> List[Update]:
    """Apply the bump ``level`` to plugin updates.

    Dependencies and properties are already constrained by the plugin (``allow*Updates``), but
    ``display-plugin-updates`` ignores those flags, so plugin proposals are filtered here. The goal
    reports intermediate same-major versions too, so the highest in-range one is still surfaced.
    """
    return [r for r in records
            if r.scope != "plugin" or within_level(r.old, r.new, level)]


def keep_upgrades(records: Iterable[Update]) -> List[Update]:
    """Drop proposals that are not strictly newer than the current version.

    ``display-plugin-updates`` groups proposals by the Maven version they require and can offer a
    *lower* version than the one in use (e.g. ``3.8.0 -> 3.6.0``); those are not real updates.
    """
    return [r for r in records if is_upgrade(r.old, r.new)]


def distinct_count(records: Iterable[Update]) -> int:
    records = keep_upgrades(records)
    deps = {r.name for r in records if r.scope in ("deps", "depmgmt")}
    plugins = {r.name for r in records if r.scope == "plugin"}
    props = {r.name for r in records if r.scope == "property"}
    return len(deps) + len(plugins) + len(props)


def _dedup_by_name(records: Iterable[Update]) -> List[Row]:
    """Keep one row per name, choosing the highest proposed version."""
    best = {}
    for r in keep_upgrades(records):
        cur = best.get(r.name)
        if cur is None or compare(r.new, cur[1]) > 0:
            best[r.name] = (r.old, r.new)
    return [(name, ov[0], ov[1]) for name, ov in best.items()]


def _fmt_rows(rows: List[Row], origins: Optional[Origins] = None,
              boms: Optional[Set[str]] = None) -> List[str]:
    """Return aligned, non-wrapped text lines for ``(name, old, new)`` rows.

    When ``origins`` is given (dependency sections only), each row is annotated with how the
    dependency enters the tree: ``[direct]``, ``[via <root dependency>]``, or ``[bom import]``
    for imported BOMs (which never appear in ``dependency:tree``).
    """
    if not rows:
        return []
    name_w = max(len(n) for n, _, _ in rows)
    old_w = max(len(o) for _, o, _ in rows)
    if origins is None:
        return [f"  {name.ljust(name_w)}  {old.rjust(old_w)} -> {new}"
                for name, old, new in sorted(set(rows))]

    def label(name: str) -> str:
        if boms and name in boms:
            return "bom import"
        return origin_label(name, origins)

    new_w = max(len(n) for _, _, n in rows)
    return [f"  {name.ljust(name_w)}  {old.rjust(old_w)} -> {new.ljust(new_w)}  [{label(name)}]"
            for name, old, new in sorted(set(rows))]


def _header(project: str, level: str, records: Iterable[Update]) -> List[str]:
    records = list(records)
    return [
        f"# Maven available updates (level={level})  generated {datetime.date.today().isoformat()}",
        f"# project: {os.path.abspath(project)}",
        f"# distinct updates: {distinct_count(records)}",
    ]


def render_unique(records: List[Update], header: List[str],
                  origins: Optional[Origins] = None,
                  boms: Optional[Set[str]] = None) -> str:
    deps = [r for r in records if r.scope in ("deps", "depmgmt")]
    plugins = [r for r in records if r.scope == "plugin"]
    props = [r for r in records if r.scope == "property"]
    lines = list(header)
    # origin annotations apply to dependencies only (not plugins/properties)
    for title, recs, orig in (("Dependencies", deps, origins),
                              ("Plugins", plugins, None),
                              ("Properties", props, None)):
        rows = _fmt_rows(_dedup_by_name(recs), orig, boms)
        lines.append("")
        lines.append(f"== {title} ({len(rows)}) ==")
        lines.extend(rows if rows else ["  (none)"])
    return "\n".join(lines) + "\n"


def render_modules(records: List[Update], parents: List[str], managed: Set[str],
                   header: List[str], origins_by_module: Optional[ModuleOrigins] = None,
                   boms: Optional[Set[str]] = None) -> str:
    by_module = {}
    for r in records:
        by_module.setdefault(r.module, []).append(r)
    merged = merge_origins(origins_by_module) if origins_by_module else None

    lines = list(header)
    lines.append("")
    lines.append("# Shared (parent-managed) updates are listed once under the parent module;")
    lines.append("# child modules show only their own, non-managed updates.")

    shared_dm, shared_plugins, shared_props = [], [], []
    for r in records:
        if r.scope == "depmgmt" or (r.scope == "deps" and r.name in managed):
            shared_dm.append(r)
        elif r.scope == "plugin":
            shared_plugins.append(r)
        elif r.scope == "property":
            shared_props.append(r)

    parent_label = parents[0] if parents else "(parent)"
    lines.append("")
    lines.append(f"[{parent_label}]  (shared)")
    # shared (parent) section: annotate deps with project-wide (merged) origins
    for title, recs, orig in (("Dependency Management", shared_dm, merged),
                              ("Plugins", shared_plugins, None),
                              ("Properties", shared_props, None)):
        rows = _fmt_rows(_dedup_by_name(recs), orig, boms)
        if rows:
            lines.append(f"  {title}:")
            lines.extend("  " + ln for ln in rows)

    for module in sorted(by_module):
        if module in parents:
            continue
        own = [r for r in by_module[module] if r.scope == "deps" and r.name not in managed]
        # child sections: use the module's own tree (fall back to merged if absent)
        mod_origins = None
        if origins_by_module is not None:
            mod_origins = origins_by_module.get(module, merged)
        rows = _fmt_rows(_dedup_by_name(own), mod_origins, boms)
        if not rows:
            continue
        lines.append("")
        lines.append(f"[{module}]")
        lines.append("  Dependencies:")
        lines.extend("  " + ln for ln in rows)
    return "\n".join(lines) + "\n"


def write_reports(records: List[Update], project: str, out_path: str, modules_out_path: str,
                  level: str, origins_by_module: Optional[ModuleOrigins] = None) -> int:
    """Write both report files (overwriting). Returns the distinct-update count."""
    from .parse import scan_project
    parents, managed, boms = scan_project(project)
    header = _header(project, level, records)
    merged = merge_origins(origins_by_module) if origins_by_module else None
    _write(out_path, render_unique(records, header, merged, boms))
    _write(modules_out_path,
           render_modules(records, parents, managed, header, origins_by_module, boms))
    return distinct_count(records)


def _write(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:  # truncates / overwrites each run
        fh.write(text)
