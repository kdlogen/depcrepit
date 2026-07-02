"""Offline tests for dependency:tree parsing and origin annotation."""
from mvn_updates.deptree import Origin, merge_origins, origin_label, parse_tree_text
from mvn_updates.parse import Update
from mvn_updates.report import render_unique

SAMPLE = r"""
[INFO] --- maven-dependency-plugin:3.7.0:tree (default-cli) @ demo-parent ---
[INFO] com.example.demo:demo-parent:pom:1.0.0-SNAPSHOT
[INFO] --- maven-dependency-plugin:3.7.0:tree (default-cli) @ module-a ---
[INFO] com.example.demo:module-a:jar:1.0.0-SNAPSHOT
[INFO] +- org.apache.commons:commons-lang3:jar:3.9:compile
[INFO] +- com.google.guava:guava:jar:30.0-jre:compile
[INFO] |  +- com.google.guava:failureaccess:jar:1.0.1:compile
[INFO] |  \- com.google.code.findbugs:jsr305:jar:3.0.2:compile
[INFO] \- org.slf4j:slf4j-api:jar:1.7.30:compile
[INFO] --- maven-dependency-plugin:3.7.0:tree (default-cli) @ module-b ---
[INFO] com.example.demo:module-b:jar:1.0.0-SNAPSHOT
[INFO] +- org.slf4j:slf4j-api:jar:1.7.30:compile
[INFO] +- junit:junit:jar:4.12:test
[INFO] |  \- org.hamcrest:hamcrest-core:jar:1.3:test
[INFO] \- commons-io:commons-io:jar:2.6:compile
"""


def test_parse_tree_direct_and_transitive():
    per_module = parse_tree_text(SAMPLE)
    a, b = per_module["module-a"], per_module["module-b"]

    assert a["org.apache.commons:commons-lang3"].direct
    assert a["com.google.guava:guava"].direct
    # transitive under guava, attributed to the depth-1 root
    assert not a["com.google.guava:failureaccess"].direct
    assert a["com.google.guava:failureaccess"].roots == {"com.google.guava:guava"}
    assert a["com.google.code.findbugs:jsr305"].roots == {"com.google.guava:guava"}

    assert b["junit:junit"].direct
    assert not b["org.hamcrest:hamcrest-core"].direct
    assert b["org.hamcrest:hamcrest-core"].roots == {"junit:junit"}


def test_merge_direct_anywhere_wins():
    per_module = parse_tree_text(SAMPLE)
    merged = merge_origins(per_module)
    assert merged["org.slf4j:slf4j-api"].direct          # direct in both modules
    assert not merged["org.hamcrest:hamcrest-core"].direct
    assert merged["org.hamcrest:hamcrest-core"].roots == {"junit:junit"}


def test_origin_labels():
    merged = merge_origins(parse_tree_text(SAMPLE))
    assert origin_label("junit:junit", merged) == "direct"
    assert origin_label("org.hamcrest:hamcrest-core", merged) == "via junit:junit"
    assert origin_label("com.example:not-in-tree", merged) == "managed, unused"


def test_render_unique_annotates_dependencies_only():
    merged = merge_origins(parse_tree_text(SAMPLE))
    records = [
        Update("depmgmt", "demo-parent", "org.hamcrest:hamcrest-core", "1.3", "2.2"),
        Update("deps", "module-b", "junit:junit", "4.12", "4.13.2"),
        Update("plugin", "demo-parent",
               "org.apache.maven.plugins:maven-surefire-plugin", "2.22.0", "3.5.4"),
    ]
    text = render_unique(records, [], merged)
    assert "[via junit:junit]" in text
    assert "[direct]" in text
    # plugins are never annotated
    plugin_line = next(ln for ln in text.splitlines() if "surefire" in ln)
    assert "[" not in plugin_line


def test_render_unique_without_origins_unchanged():
    records = [Update("deps", "m", "junit:junit", "4.12", "4.13.2")]
    text = render_unique(records, [])
    assert "junit:junit" in text and "[" not in text.split("==")[1]
