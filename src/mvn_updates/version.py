"""A pragmatic Maven-style version comparison.

This is *not* a full reimplementation of Maven's ``ComparableVersion`` but is faithful for the cases
that matter here: numeric dotted versions with an optional trailing qualifier (``-beta4``, ``-jre``,
``-M1``, ``-SNAPSHOT`` …). It is used to drop "updates" whose proposed version is not strictly newer
than the current one (e.g. ``display-plugin-updates`` can propose a *lower*, more Maven-compatible
plugin version), and to pick the highest proposal when several are offered for one artifact.
"""
from __future__ import annotations

import re

# Known qualifier ranks (lower = older). A release (no/empty qualifier) ranks above pre-releases.
_QUAL = {
    "alpha": -5, "a": -5,
    "beta": -4, "b": -4,
    "milestone": -3, "m": -3,
    "rc": -2, "cr": -2,
    "snapshot": -1,
    "": 0, "ga": 0, "final": 0, "release": 0,
    "sp": 1,
}


def _split(v: str):
    v = (v or "").strip().lower()
    m = re.match(r"\d+(?:\.\d+)*", v)
    if m:
        nums = [int(x) for x in m.group(0).split(".")]
        rest = v[m.end():]
    else:
        nums, rest = [], v
    return nums, rest.lstrip(".-_+")


def _qual_rank(q: str) -> int:
    if not q:
        return 0
    word = re.match(r"[a-z]+", q)
    return _QUAL.get(word.group(0) if word else q, 0)


def compare(a: str, b: str) -> int:
    """Return -1, 0, or 1 for ``a`` <, ==, > ``b`` under Maven-ish ordering."""
    na, qa = _split(a)
    nb, qb = _split(b)
    n = max(len(na), len(nb))
    na += [0] * (n - len(na))
    nb += [0] * (n - len(nb))
    if na != nb:
        return -1 if na < nb else 1
    ra, rb = _qual_rank(qa), _qual_rank(qb)
    if ra != rb:
        return -1 if ra < rb else 1
    if qa != qb:
        return -1 if qa < qb else 1
    return 0


def is_upgrade(old: str, new: str) -> bool:
    """True only when ``new`` is strictly newer than ``old``."""
    return compare(new, old) > 0


def _release_nums(v: str):
    nums, _qual = _split(v)
    while len(nums) < 3:
        nums.append(0)
    return nums


def bump_level(old: str, new: str) -> str:
    """Classify the change as ``major``, ``minor`` or ``patch`` by numeric components."""
    o, n = _release_nums(old), _release_nums(new)
    if n[0] != o[0]:
        return "major"
    if n[1] != o[1]:
        return "minor"
    return "patch"


def within_level(old: str, new: str, level: str) -> bool:
    """Whether the ``old -> new`` change is allowed at the requested bump ``level``."""
    if level == "major":
        return True
    b = bump_level(old, new)
    if level == "minor":
        return b in ("minor", "patch")
    if level == "bugfix":
        return b == "patch"
    return True
