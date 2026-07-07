import os

from depcrepit.parse import (
    Update,
    parse_log_file,
    required_width,
    resolve_versions,
    scan_project,
    scan_properties,
)
from depcrepit.report import (
    distinct_count,
    keep_upgrades,
    render_modules,
    render_unique,
    write_reports,
    _header,
)

HERE = os.path.dirname(__file__)
LOG = os.path.join(HERE, "data", "sample-maven.log")
PROJECT = os.path.join(HERE, "fixtures", "multimodule")


def _records():
    return parse_log_file(LOG)


def test_parse_scopes_and_modules():
    records = _records()
    by = {(r.scope, r.name, r.module) for r in records}
    assert ("depmgmt", "com.google.guava:guava", "demo-parent") in by
    assert ("deps", "commons-io:commons-io", "module-b") in by
    assert ("plugin", "maven-surefire-plugin", "demo-parent") in by
    assert ("property", "${junit.version}", "demo-parent") in by


def test_parse_handles_wrapped_entry():
    records = _records()
    wrapped = [r for r in records
               if r.name == "org.example.really.long.group:an-extremely-long-artifact-id-that-wraps"]
    assert len(wrapped) == 1
    assert (wrapped[0].old, wrapped[0].new) == ("1.0.0", "2.0.0")


def test_required_width_detects_long_entry():
    # the wrapped artifact id is well over 80 chars -> needs a wider line
    assert required_width(_records()) > 80


def test_unique_report_dedupes_across_modules():
    records = _records()
    text = render_unique(records, _header(PROJECT, "major", records))
    # slf4j is referenced by parent + both modules but must appear once
    assert text.count("org.slf4j:slf4j-api") == 1
    assert "== Dependencies (" in text
    assert "maven-surefire-plugin" in text
    assert "${junit.version}" in text


def test_scan_project_finds_parent_managed_and_boms():
    parents, managed, boms = scan_project(PROJECT)
    assert "demo-parent" in parents
    assert "com.google.guava:guava" in managed
    assert "org.slf4j:slf4j-api" in managed
    assert "commons-io:commons-io" not in managed  # module-specific, not managed
    # type=pom + scope=import entries are recognised as BOM imports
    assert "com.fasterxml.jackson:jackson-bom" in boms
    assert "com.google.guava:guava" not in boms


def test_scan_properties_reads_all_poms():
    props = scan_properties(PROJECT)
    assert props["junit.version"] == "4.12"
    assert props["jackson.version"] == "2.13.0"


def test_resolve_versions_drops_noop_property_rows():
    # raw-model BOM row: current version is an unresolved property that already holds the
    # proposed version -> after resolution the row is a no-op and must be filtered out
    props = {"wildfly.version": "26.1.3.Final"}
    recs = resolve_versions(
        [Update("depmgmt", "root", "org.wildfly.bom:wildfly-jakartaee8-with-tools",
                "${wildfly.version}", "26.1.3.Final")], props)
    assert recs[0].old == "26.1.3.Final"
    assert keep_upgrades(recs) == []


def test_resolve_versions_keeps_real_updates_and_unknown_properties():
    props = {"netty.version": "4.1.135.Final"}
    real, unknown = resolve_versions(
        [Update("depmgmt", "root", "io.netty:netty-bom", "${netty.version}", "4.2.16.Final"),
         Update("depmgmt", "root", "g:a", "${no.such.property}", "2.0")], props)
    assert (real.old, real.new) == ("4.1.135.Final", "4.2.16.Final")
    assert keep_upgrades([real]) == [real]
    assert unknown.old == "${no.such.property}"  # left untouched


def test_modules_report_extracts_parent_and_isolates_module_specific():
    records = _records()
    parents, managed, _boms = scan_project(PROJECT)
    text = render_modules(records, parents, managed, _header(PROJECT, "major", records))
    # parent section holds the shared/managed entries
    assert "[demo-parent]" in text
    assert "Dependency Management:" in text
    # commons-io is module-specific -> only under module-b
    assert "[module-b]" in text
    b_section = text.split("[module-b]", 1)[1]
    assert "commons-io:commons-io" in b_section
    # module-a has no module-specific deps -> no section
    assert "[module-a]" not in text


def test_write_reports_creates_missing_parent_dirs(tmp_path):
    out = tmp_path / "reports" / "updates-minor.txt"   # 'reports/' does not exist yet
    count = write_reports(_records(), PROJECT, str(out), str(out) + "-modules", "minor")
    assert out.exists()
    assert count > 0


def test_distinct_count():
    # 5 distinct dep names (guava, slf4j, commons-lang3, junit, commons-io) + long wrapped one
    # + 1 plugin + 1 property
    records = _records()
    assert distinct_count(records) == len(
        {r.name for r in records if r.scope in ("deps", "depmgmt")}
    ) + 1 + 1
