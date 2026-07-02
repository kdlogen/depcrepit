from depcrepit.parse import Update
from depcrepit.report import enforce_level, keep_upgrades, render_unique, _header
from depcrepit.version import bump_level, compare, is_upgrade, within_level


def test_compare_numeric():
    assert compare("3.8.0", "3.6.0") > 0
    assert compare("3.6.0", "3.8.0") < 0
    assert compare("1.0", "1.0.0") == 0
    assert compare("2.22.0", "2.6") > 0       # not lexical: 22 > 6


def test_compare_qualifiers():
    assert compare("1.8.0", "1.8.0-beta4") > 0      # release newer than pre-release
    assert compare("2.0.0-alpha1", "2.0.0-beta1") < 0
    assert compare("1.0-SNAPSHOT", "1.0") < 0


def test_is_upgrade():
    assert is_upgrade("3.6.0", "3.8.0") is True
    assert is_upgrade("3.8.0", "3.6.0") is False    # the reported downgrade
    assert is_upgrade("1.0", "1.0") is False


def test_bump_level():
    assert bump_level("1.3.1", "2.0.3") == "major"
    assert bump_level("2.22.0", "2.30.0") == "minor"
    assert bump_level("2.22.0", "2.22.2") == "patch"
    assert bump_level("1.0", "2.0") == "major"


def test_within_level():
    assert within_level("1.3.1", "2.0.3", "major") is True
    assert within_level("1.3.1", "2.0.3", "minor") is False    # the jgiven case
    assert within_level("2.22.0", "2.22.2", "minor") is True
    assert within_level("2.22.0", "2.30.0", "minor") is True
    assert within_level("2.22.0", "2.30.0", "bugfix") is False
    assert within_level("2.22.0", "2.22.2", "bugfix") is True


def test_enforce_level_filters_plugins_only():
    records = [
        Update("plugin", "p", "com.tngtech.jgiven:jgiven-maven-plugin", "1.3.1", "2.0.3"),
        Update("plugin", "p", "maven-surefire-plugin", "2.22.0", "2.22.2"),
        # deps/properties are left untouched (already constrained by the plugin's allow*Updates)
        Update("deps", "p", "some:lib", "1.0.0", "2.0.0"),
        Update("property", "p", "${x.version}", "1.0.0", "2.0.0"),
    ]
    kept = enforce_level(records, "minor")
    plugins = {r.name for r in kept if r.scope == "plugin"}
    assert "com.tngtech.jgiven:jgiven-maven-plugin" not in plugins   # major bump dropped
    assert "maven-surefire-plugin" in plugins                        # patch bump kept
    assert any(r.scope == "deps" for r in kept)                      # dep untouched
    assert any(r.scope == "property" for r in kept)                  # property untouched


def test_downgrade_filtered_and_highest_kept():
    records = [
        # the display-plugin-updates downgrade case + the real upgrade for the same plugin
        Update("plugin", "demo-parent", "maven-assembly-plugin", "3.7.1", "3.6.0"),
        Update("plugin", "demo-parent", "maven-assembly-plugin", "3.7.1", "3.8.0"),
        # a plugin whose only proposal is a downgrade -> must disappear entirely
        Update("plugin", "demo-parent", "maven-foo-plugin", "9.0.0", "8.0.0"),
    ]
    assert {r.new for r in keep_upgrades(records)} == {"3.8.0"}
    text = render_unique(records, _header(".", "major", records))
    assert "3.7.1 -> 3.8.0" in text
    assert "3.6.0" not in text          # downgrade dropped
    assert "maven-foo-plugin" not in text
    assert "== Plugins (1) ==" in text  # only the one real upgrade
