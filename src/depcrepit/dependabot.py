"""Convert a Dependabot config (``dependabot.yml``) into a versions-maven-plugin ruleset.

Only the *version constraints* and *dependency-name wildcards* of the ``ignore`` entries are
converted:

* ``dependency-name`` + ``versions`` -> a ``<rule>`` with ``<ignoreVersion>`` children
  (``range`` / ``regex`` / ``exact``). A ``versions`` entry of ``"*"`` means *any version*.
* ``dependency-name`` with **no** ``versions`` (and no ``update-types``) -> ignore *all* versions
  of that dependency (regex ``.*``), matching Dependabot's "block this dependency entirely".
* ``dependency-name: "*"`` -> the ignore applies as a top-level (global) ``<ignoreVersions>``.

``update-types`` are intentionally ignored (out of scope); an entry that has *only* ``update-types``
(no ``versions``) is skipped.
``*`` wildcards in ``dependency-name`` are passed straight through to the ruleset, which matches
them natively in both ``groupId`` and ``artifactId``.

No third-party dependency is required: PyYAML is used when available, otherwise a small
Dependabot-shaped YAML parser is used.
"""
from __future__ import annotations

import re
from typing import List, Tuple
from xml.sax.saxutils import escape

RULESET_NS = "https://www.mojohaus.org/VERSIONS/RULE/3.0.0"
_GLOBAL_NAMES = {"*", "*:*", ":"}

# A rule is (groupId, artifactId, [(ignore_type, ignore_value), ...]).
Rule = Tuple[str, str, List[Tuple[str, str]]]
Ignore = Tuple[str, str]


# --------------------------------------------------------------------------- YAML loading
def load_yaml(text: str):
    """Parse YAML text, preferring PyYAML and falling back to the built-in mini-parser."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return _MiniYaml(text).parse()


class _MiniYaml:
    """Minimal indentation-based YAML parser, good enough for Dependabot configs.

    Supports block mappings, block sequences (``- ...``), inline flow sequences (``[a, b]``),
    quoted/unquoted scalars, and full-line / trailing ``#`` comments.
    """

    def __init__(self, text: str):
        self.lines = []
        for raw in text.splitlines():
            stripped = _strip_comment(raw)
            if stripped.strip() == "":
                continue
            indent = len(stripped) - len(stripped.lstrip(" "))
            self.lines.append((indent, stripped.strip()))
        self.i = 0

    def parse(self):
        if not self.lines:
            return None
        return self._block(self.lines[0][0])

    def _block(self, indent):
        if self.i < len(self.lines) and self.lines[self.i][0] == indent \
                and self.lines[self.i][1].startswith("- "):
            return self._sequence(indent)
        return self._mapping(indent)

    def _mapping(self, indent):
        result = {}
        while self.i < len(self.lines):
            cur_indent, content = self.lines[self.i]
            if cur_indent < indent or content.startswith("- "):
                break
            if cur_indent > indent:  # defensive: skip deeper stray lines
                self.i += 1
                continue
            key, _, rest = content.partition(":")
            key = _unquote(key.strip())
            rest = rest.strip()
            self.i += 1
            if rest == "":
                if self.i < len(self.lines) and self.lines[self.i][0] > indent:
                    result[key] = self._block(self.lines[self.i][0])
                else:
                    result[key] = None
            else:
                result[key] = _scalar_or_flow(rest)
        return result

    def _sequence(self, indent):
        items = []
        while self.i < len(self.lines):
            cur_indent, content = self.lines[self.i]
            if cur_indent != indent or not content.startswith("- "):
                break
            inner = content[2:]  # drop "- "
            item_indent = indent + 2
            if ":" in inner and not inner.startswith("["):
                # mapping whose first key sits on the "- " line; rewrite and recurse
                self.lines[self.i] = (item_indent, inner)
                items.append(self._mapping(item_indent))
            else:
                self.i += 1
                items.append(_scalar_or_flow(inner.strip()))
        return items


def _strip_comment(line: str) -> str:
    out, in_quote = [], None
    for ch in line:
        if in_quote:
            out.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] == " "):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _scalar_or_flow(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_unquote(p.strip()) for p in inner.split(",")]
    return _unquote(s)


# --------------------------------------------------------------------------- conversion
def version_to_ignore(spec: str) -> Ignore:
    """Map one Dependabot ``versions`` entry to an ``(type, value)`` ``<ignoreVersion>`` pair."""
    spec = spec.strip()
    if spec in ("*", "=*"):  # "any version" -> ignore everything
        return ("regex", ".*")
    m = re.match(r"^(>=|<=|>|<|=)\s*(.+)$", spec)
    if m:
        op, ver = m.group(1), m.group(2).strip()
        if ver == "*":
            return ("regex", ".*")
        return {
            ">=": ("range", f"[{ver},)"),
            ">": ("range", f"({ver},)"),
            "<=": ("range", f"(,{ver}]"),
            "<": ("range", f"(,{ver})"),
            "=": ("exact", ver),
        }[op]
    if re.search(r"\.(x|\*)$", spec):  # wildcard form: 1.x / 1.* / 2.6.x
        prefix = re.sub(r"\.(x|\*)$", "", spec)
        return ("regex", re.escape(prefix) + r"\..*")
    return ("exact", spec)


def split_dependency_name(name: str) -> Tuple[str, str]:
    """Split a Dependabot maven name ``groupId:artifactId`` (``*`` wildcards passed through)."""
    if ":" in name:
        group, artifact = name.split(":", 1)
    else:
        group, artifact = name, "*"
    return group.strip(), artifact.strip()


def build_ruleset(cfg) -> Tuple[List[Rule], List[Ignore]]:
    """Turn a parsed Dependabot config into ``(rules, global_ignores)``."""
    rules: List[Rule] = []
    global_ignores: List[Ignore] = []

    updates = (cfg or {}).get("updates") or []
    if isinstance(updates, dict):
        updates = [updates]
    for block in updates:
        if not isinstance(block, dict):
            continue
        if str(block.get("package-ecosystem", "")).strip() != "maven":
            continue
        for ig in (block.get("ignore") or []):
            if not isinstance(ig, dict):
                continue
            name = str(ig.get("dependency-name", "*")).strip()
            versions = ig.get("versions") or []
            if isinstance(versions, str):
                versions = [versions]
            update_types = ig.get("update-types") or []

            if versions:
                ignores = [version_to_ignore(v) for v in versions]
            elif update_types:
                # update-types-only entries are out of scope (see module docstring) -> skip
                continue
            else:
                # dependency-name only -> ignore ALL versions (Dependabot semantics)
                ignores = [("regex", ".*")]

            if name in _GLOBAL_NAMES:
                global_ignores.extend(ignores)
            else:
                group, artifact = split_dependency_name(name)
                rules.append((group, artifact, ignores))
    return rules, global_ignores


def ruleset_xml(rules: List[Rule], global_ignores: List[Ignore]) -> str:
    """Render a ruleset XML document from rules + global ignores."""
    def ignore_block(items, indent):
        pad = " " * indent
        out = [f"{pad}<ignoreVersions>"]
        for typ, val in items:
            out.append(f'{pad}  <ignoreVersion type="{typ}">{escape(val)}</ignoreVersion>')
        out.append(f"{pad}</ignoreVersions>")
        return "\n".join(out)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<ruleset xmlns="{RULESET_NS}">']
    if global_ignores:
        lines.append(ignore_block(global_ignores, 2))
    lines.append("  <rules>")
    for group, artifact, items in rules:
        attrs = f'groupId="{escape(group)}"'
        if artifact and artifact != "*":
            attrs += f' artifactId="{escape(artifact)}"'
        lines.append(f"    <rule {attrs}>")
        lines.append(ignore_block(items, 6))
        lines.append("    </rule>")
    lines.append("  </rules>")
    lines.append("</ruleset>")
    return "\n".join(lines) + "\n"


def rules_from_file(path: str) -> Tuple[List[Rule], List[Ignore]]:
    """Read a ``dependabot.yml`` file and return ``(rules, global_ignores)``."""
    with open(path, encoding="utf-8") as fh:
        return build_ruleset(load_yaml(fh.read()))


def convert_text(text: str) -> str:
    """Convert Dependabot YAML *text* to ruleset XML text."""
    rules, global_ignores = build_ruleset(load_yaml(text))
    return ruleset_xml(rules, global_ignores)


def convert_file(dependabot_path: str, out_path: str) -> str:
    """Read a ``dependabot.yml`` file and write the ruleset XML to ``out_path``."""
    with open(dependabot_path, encoding="utf-8") as fh:
        xml = convert_text(fh.read())
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return out_path
