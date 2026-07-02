"""Built-in version-ignore patterns for filtering non-stable / unofficial versions.

Each entry is a **full-match** (anchored), case-insensitive regex suitable for a
versions-maven-plugin ``<ignoreVersion type="regex">``. The plugin matches the regex against the
*entire* candidate version string, so patterns are written as ``.*marker.*``.

These deliberately do NOT match stable GA qualifiers such as ``.Final``, ``.RELEASE`` or ``.GA``
(Spring/Hibernate use those for official releases). Vendor forks (e.g. ``-atlassian``, ``-redhat``)
are project-specific and are left to the user via ``--ignore-version``.
"""
from __future__ import annotations

from typing import List, Tuple

Ignore = Tuple[str, str]

# Semantic pre-release qualifiers. Each requires a separator (-, ., _) before the keyword so that
# stable GA markers (.Final, .RELEASE, .GA) and build metadata (-jre, -android) are NOT matched.
STABLE_ONLY_PATTERNS: List[str] = [
    r"(?i).*[-._]alpha.*",
    r"(?i).*[-._]beta.*",
    r"(?i).*[-._]milestone.*",   # word form: -milestone1
    r"(?i).*[-._]m\d+.*",        # short milestone: -M4 / .M4
    r"(?i).*[-._]rc\d*.*",       # release candidate: -RC1 / .RC1
    r"(?i).*[-._]cr\d*.*",       # (older) candidate release: .CR1
    r"(?i).*[-._]snapshot.*",
    r"(?i).*[-._]preview.*",
    r"(?i).*[-._]pre\d+.*",      # -pre1
    r"(?i).*[-._]dev\d*.*",      # -dev / -dev2
    r"(?i).*[-._]incubating.*",
    r"(?i).*[-._](ea|eap)\d*.*", # early access / early-access preview
    r"(?i).*[-._]canary.*",
    r"(?i).*[-._]nightly.*",
]


# Third-party redistribution / vendor-fork qualifiers (a stable upstream version, repackaged).
# These are never the canonical upstream release, so they are ignored by default; opt out with
# --allow-vendor-forks, or add your own with --ignore-version.
VENDOR_FORK_PATTERNS: List[str] = [
    r"(?i).*[-._]atlassian[-._.].*",   # 3.141.59-atlassian-1
    r"(?i).*[-._]redhat[-._.].*",      # x.y.z-redhat-00001
    r"(?i).*[-._]jbossorg[-._.].*",
    r"(?i).*[-._]mulesoft[-._.].*",
]


def as_ignores(patterns: List[str]) -> List[Ignore]:
    """Wrap regex strings as ``("regex", pattern)`` ignore tuples."""
    return [("regex", p) for p in patterns]
