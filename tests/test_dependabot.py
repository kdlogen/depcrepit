import xml.etree.ElementTree as ET

from depcrepit.dependabot import (
    build_ruleset,
    convert_text,
    load_yaml,
    split_dependency_name,
    version_to_ignore,
)

SAMPLE = """\
version: 2
updates:
  - package-ecosystem: "maven"
    directory: "/"
    schedule:
      interval: "weekly"
    ignore:
      - dependency-name: "com.google.guava:guava"
        versions: [">=33.0"]
      - dependency-name: "commons-io:commons-io"
        versions: ["2.6.x"]
      - dependency-name: "org.slf4j:*"
        versions: [">=1.8"]
      - dependency-name: "org.skip:me"
        update-types: ["version-update:semver-major"]
      - dependency-name: "*"
        versions: ["<1.0"]
"""


def test_version_to_ignore():
    assert version_to_ignore(">=33.0") == ("range", "[33.0,)")
    assert version_to_ignore("> 2") == ("range", "(2,)")
    assert version_to_ignore("<=1.5") == ("range", "(,1.5]")
    assert version_to_ignore("<2.0") == ("range", "(,2.0)")
    assert version_to_ignore("=1.2.3") == ("exact", "1.2.3")
    assert version_to_ignore("1.2.3") == ("exact", "1.2.3")
    assert version_to_ignore("2.6.x") == ("regex", r"2\.6\..*")
    assert version_to_ignore("1.*") == ("regex", r"1\..*")


def test_split_dependency_name_keeps_wildcards():
    assert split_dependency_name("org.slf4j:*") == ("org.slf4j", "*")
    assert split_dependency_name("org.springframework.*") == ("org.springframework.*", "*")
    assert split_dependency_name("commons-io:commons-io") == ("commons-io", "commons-io")


def test_build_ruleset_scopes_rules_and_globals():
    rules, global_ignores = build_ruleset(load_yaml(SAMPLE))
    names = {(g, a) for g, a, _ in rules}
    assert ("com.google.guava", "guava") in names
    assert ("commons-io", "commons-io") in names
    assert ("org.slf4j", "*") in names
    # update-types-only entry is skipped entirely
    assert ("org.skip", "me") not in names
    # dependency-name "*" with versions becomes a global ignore
    assert ("range", "(,1.0)") in global_ignores


def test_ignore_all_versions_of_a_dependency():
    # all three forms a user might write must mean "ignore every version"
    cfg = """\
version: 2
updates:
  - package-ecosystem: "maven"
    ignore:
      - dependency-name: "g1:*"
      - dependency-name: "g2:*"
        versions: ["*"]
      - dependency-name: "g3:*"
        versions: ["=*"]
"""
    rules, _ = build_ruleset(load_yaml(cfg))
    by_group = {g: ig for g, _a, ig in rules}
    assert by_group["g1"] == [("regex", ".*")]
    assert by_group["g2"] == [("regex", ".*")]
    assert by_group["g3"] == [("regex", ".*")]


def test_version_star_is_ignore_all():
    assert version_to_ignore("*") == ("regex", ".*")
    assert version_to_ignore("=*") == ("regex", ".*")
    assert version_to_ignore(">=*") == ("regex", ".*")


def test_update_types_only_entry_is_skipped():
    cfg = """\
version: 2
updates:
  - package-ecosystem: "maven"
    ignore:
      - dependency-name: "org.skip:me"
        update-types: ["version-update:semver-major"]
"""
    rules, global_ignores = build_ruleset(load_yaml(cfg))
    assert rules == [] and global_ignores == []


def test_convert_text_produces_valid_xml_with_expected_rules():
    xml = convert_text(SAMPLE)
    root = ET.fromstring(xml)  # must be well-formed
    ns = "{https://www.mojohaus.org/VERSIONS/RULE/3.0.0}"
    rule_groups = {r.get("groupId") for r in root.iter(f"{ns}rule")}
    assert {"com.google.guava", "commons-io", "org.slf4j"} <= rule_groups
    # slf4j wildcard rule has no artifactId attribute (matches all artifacts)
    slf4j = [r for r in root.iter(f"{ns}rule") if r.get("groupId") == "org.slf4j"][0]
    assert slf4j.get("artifactId") is None
    ignore_types = {iv.get("type") for iv in root.iter(f"{ns}ignoreVersion")}
    assert {"range", "regex"} <= ignore_types
