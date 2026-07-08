import re
import xml.etree.ElementTree as ET

from depcrepit.dependabot import ruleset_xml
from depcrepit.ignores import (COMPAT_VARIANT_PATTERNS, DATE_STAMP_PATTERNS,
                               STABLE_ONLY_PATTERNS, VENDOR_FORK_PATTERNS, as_ignores)

NS = "{https://www.mojohaus.org/VERSIONS/RULE/3.0.0}"


def _matches_any(version, patterns):
    # mirrors the plugin's full-match semantics for type="regex"
    return any(re.fullmatch(p, version) for p in patterns)


def test_stable_only_catches_prereleases():
    for v in ["3.7.0-M4", "2.0.0-alpha1", "1.8.0-beta4", "5.0.0.RC1",
              "1.0-SNAPSHOT", "6.0.0-preview", "4.0.0.CR1",
              "1.0.0-milestone1", "2.0.0-dev3", "3.0.0-incubating",
              "11.0.0-ea", "1.0.0-canary", "4.0.0-nightly",
              "3.0.1-b12", "2.3.1-b02"]:  # glassfish/jaxb promoted beta builds
        assert _matches_any(v, STABLE_ONLY_PATTERNS), v


def test_date_stamp_versions_caught():
    # pure dates and maven-1 date.time stamps
    for v in ["20040616", "20030911", "19991231", "20040102.233541"]:
        assert _matches_any(v, DATE_STAMP_PATTERNS), v


def test_date_stamp_spares_normal_and_calendar_versions():
    # calendar-style (2024.1), x.y.z and non-date 8-digit strings must NOT be ignored
    for v in ["3.2.2", "2024.1", "2024.1.2", "20240132", "1.20040616"]:
        assert not _matches_any(v, DATE_STAMP_PATTERNS), v


def test_compat_variants_caught():
    for v in ["1.18.11-jdk5", "1.18.11.jdk8", "2.0-JDK6"]:
        assert _matches_any(v, COMPAT_VARIANT_PATTERNS), v


def test_compat_variants_spare_primary_flavors():
    # -jre / -android are the primary line for some artifacts (guava) and must survive
    for v in ["33.6.0-jre", "33.6.0-android", "1.18.11", "5.6.15.Final"]:
        assert not _matches_any(v, COMPAT_VARIANT_PATTERNS), v


def test_stable_only_spares_official_releases():
    # GA markers, build metadata and plain releases must NOT be ignored
    for v in ["5.6.15.Final", "6.1.2", "5.3.39", "30.1.1-jre", "2.22.0",
              "6.0.0.RELEASE", "3.4.0-android", "1.2.3.GA"]:
        assert not _matches_any(v, STABLE_ONLY_PATTERNS), v


def test_vendor_forks_caught_by_default():
    for v in ["3.141.59-atlassian-1", "5.6.15.Final-atlassian-4",
              "1.2.3-redhat-00001", "2.0.0-jbossorg-1"]:
        assert _matches_any(v, VENDOR_FORK_PATTERNS), v


def test_vendor_forks_spare_official_releases():
    for v in ["3.141.59", "5.6.15.Final", "1.2.3", "30.1.1-jre"]:
        assert not _matches_any(v, VENDOR_FORK_PATTERNS), v


def test_vendor_fork_custom_pattern():
    pat = r"(?i).*atlassian.*"
    assert re.fullmatch(pat, "5.3.39-atlassian-10")
    assert re.fullmatch(pat, "5.6.15.Final-atlassian-4")   # .Final stays; -atlassian triggers it
    assert not re.fullmatch(pat, "5.6.15.Final")


def test_ruleset_xml_global_ignores_are_wellformed_regex():
    xml = ruleset_xml([], as_ignores(STABLE_ONLY_PATTERNS + [r"(?i).*atlassian.*"]))
    root = ET.fromstring(xml)
    ignore_versions = list(root.iter(f"{NS}ignoreVersion"))
    assert ignore_versions  # global <ignoreVersions> present even with no rules
    assert all(iv.get("type") == "regex" for iv in ignore_versions)
    assert any("atlassian" in (iv.text or "") for iv in ignore_versions)
