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
    r"(?i).*[\d._-]b\d+.*",      # promoted beta build: -b12 / .b02 / 1.1b4 / -b180830.0359
                                 # (b<number> after a digit or separator; plain words like
                                 # "web2" in a qualifier are not matched)
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


# Maven-1-era date(-time)-stamp versions (commons-collections 20040616 / 20040102.233541,
# antlr 20030911, ...). Maven's version ordering treats them as numerically huge, so they get
# proposed as "upgrades" for artifacts whose real versioning is x.y.z. Full-match YYYYMMDD with
# an optional .HHMMSS part, so calendar-style versions like 2024.1 are unaffected; opt out with
# --allow-date-versions.
DATE_STAMP_PATTERNS: List[str] = [
    r"(19|20)\d{2}(0\d|1[0-2])([0-2]\d|3[01])(\.\d{1,6})?",
]


# Compatibility variant builds of an otherwise identical release (byte-buddy 1.18.11-jdk5, ...).
# The plain version is the canonical one to target; opt out with --allow-variants. Deliberately
# does NOT cover flavor qualifiers that ARE the primary line for some artifacts (-jre, -android).
COMPAT_VARIANT_PATTERNS: List[str] = [
    r"(?i).*[-._]jdk\d+.*",
]


def as_ignores(patterns: List[str]) -> List[Ignore]:
    """Wrap regex strings as ``("regex", pattern)`` ignore tuples."""
    return [("regex", p) for p in patterns]
