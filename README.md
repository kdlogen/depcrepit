# mvn-updates

Report the available **dependency / plugin / property updates** for a multi-module
[Maven](https://maven.apache.org/) project using the
[`versions-maven-plugin`](https://www.mojohaus.org/versions/), as two clean, de-duplicated text
files. Optionally filter by bump level and by a converted **Dependabot** config.

- Single, de-duplicated list across all submodules
- A per-module breakdown that **extracts parent-managed** dependencies (so `dependencyManagement` /
  `pluginManagement` / version properties are listed once under the parent, not repeated per module)
- Major / minor / bugfix bump filtering
- Converts `dependabot.yml` `ignore` version constraints + name wildcards into a versions ruleset
- **No required Python dependencies** (standard library only); the only external requirement is Maven

## Install

```bash
# from a clone / source checkout
pip install .

# or run without installing
python -m mvn_updates --help
```

Requires Python ≥ 3.8 and **Maven (`mvn`) on PATH**. `PyYAML` is optional (`pip install .[yaml]`) —
it makes Dependabot parsing more robust, but a built-in fallback parser is used when it is absent.

## Usage

```bash
mvn-updates [options]
# equivalently: python -m mvn_updates [options]
```

| Option | Description |
|----------------------|-------------------------------------------------------------------|
| `-o, --output FILE`  | Base output path (default `maven-updates.txt`). The per-module file is `<base>-modules.txt`. |
| `-p, --project DIR`  | Maven project root (default `.`). |
| `-l, --level LEVEL`  | Allowed bump level: `major` \| `minor` \| `bugfix` (default `major`). |
| `-d, --dependabot FILE` | A `dependabot.yml` to convert into a versions ruleset. |
| `--allow-prereleases` | Include non-stable versions. By **default** alpha/beta/milestone/rc/snapshot/preview/… are ignored so the latest **stable** is reported (GA markers like `.Final` / `.RELEASE` and build metadata like `-jre` are kept). |
| `--allow-vendor-forks` | Include third-party redistribution forks (`-atlassian-1`, `-redhat-00001`, …). By **default** these are ignored in favour of the canonical upstream release. |
| `--ignore-version REGEX` | Full-match regex of versions to ignore (repeatable); for any other fork/qualifier, e.g. `--ignore-version '(?i).*mycorp.*'`. |
| `-w, --line-width N` | Output line width; clamped to a minimum of **120** (default `120`). |
| `--no-plugins`       | Skip plugin updates. |
| `--no-properties`    | Skip Maven version-property updates. |
| `--plugin-version V` | `versions-maven-plugin` version (default `2.18.0`). |
| `--mvn PATH`         | Path to the `mvn` executable (default `mvn`). |
| `-V, --version`      | Print version. |

Example:

```bash
mvn-updates -p /path/to/project -o reports/updates.txt -l minor -d .github/dependabot.yml
```

Both files are **overwritten** on every run. Nothing but progress is printed to the console
(progress goes to stderr); the report goes only to the files.

## Output

### `<output>.txt` — single, de-duplicated list
Every available update across all modules merged into one list (a dependency referenced by several
modules appears once), grouped into `Dependencies`, `Plugins`, `Properties`.

### `<output>-modules.txt` — per-module breakdown with parent extraction
Updates managed in the parent (`<dependencyManagement>`, `<pluginManagement>`, version
`<properties>`) are listed once under the parent module and removed from the child modules. Each
child module then shows only its own, non-managed dependency updates; modules with nothing
module-specific are omitted.

## Dependabot conversion

For each `package-ecosystem: maven` block, the **version constraints** of the `ignore` entries are
converted into a versions ruleset (passed via `-Dmaven.version.rules`):

| Dependabot | Converted to |
|------------|--------------|
| `dependency-name` + `versions: [">=X"]` / `["<X"]` … | `<rule>` with `<ignoreVersion type="range">[X,)</…>` etc. |
| `dependency-name` + `versions: ["X.x"]` / `["X.*"]`  | `<rule>` with `<ignoreVersion type="regex">X\..*</…>` |
| `dependency-name` + `versions: ["X"]` (exact)        | `<rule>` with `<ignoreVersion type="exact">X</…>` |
| `dependency-name` **alone** (no `versions`) / `versions: ["*"]` | ignore **all** versions of that dependency (`<ignoreVersion type="regex">.*</…>`) |
| `dependency-name: "*"` + `versions`                  | top-level (global) `<ignoreVersions>` |

To ignore a whole group entirely, list the name with no version constraint (Dependabot's own
"block this dependency" form):

```yaml
ignore:
  - dependency-name: "com.example.internal:*"   # never report updates for this group
```

**Wildcards** in `dependency-name` (e.g. `org.slf4j:*`, `org.springframework.*`) are passed straight
through — the ruleset matches `*` in both `groupId` and `artifactId` natively (and `groupId` also has
an implicit trailing `.*`). `update-types` are **out of scope and ignored** — use `-l/--level` for a
project-wide limit. Entries without a `versions` constraint are skipped.

## Filtering non-stable / unofficial versions

**By default**, semantic pre-releases (alpha/beta/milestone/RC/snapshot/preview/dev/incubating/ea/…)
are ignored, so the latest **stable** version is reported instead of e.g. `3.7.0-M4`. Pass
`--allow-prereleases` to turn this off:

Common third-party **vendor forks** (`-atlassian-1`, `-redhat-00001`, `-jbossorg-1`, `-mulesoft-1`)
are *also* ignored by default — they repackage a stable upstream version (e.g. selenium
`3.141.59-atlassian-1`) and are rarely what you want. Add your own with `--ignore-version`.

```bash
mvn-updates -p .                          # stable + canonical upstream only (default)
mvn-updates -p . --allow-prereleases      # include alpha/beta/milestone/rc/...
mvn-updates -p . --allow-vendor-forks     # include -atlassian/-redhat/... forks

# ignore an additional fork/qualifier (regex is full-matched against the whole version)
mvn-updates -p . --ignore-version '(?i).*mycorp.*'
```

This works by adding global `<ignoreVersions>` regex rules to the ruleset, so the **plugin** skips
those candidates and resolves the newest acceptable one — it is *not* a post-filter (which would
wrongly hide a dependency whose only reported candidate was a pre-release/fork). The default filter
deliberately keeps GA qualifiers like `.Final`, `.RELEASE`, `.GA` and build metadata like `-jre`;
what makes `5.6.15.Final-atlassian-4` unofficial is the vendor `-atlassian` suffix. All of this
combines with `-d/--dependabot`.

> **Plugin proposals / downgrades / level:** `display-plugin-updates` groups proposals by the Maven
> version they require, can list a version *lower* than the one in use (e.g. `3.8.0 -> 3.6.0`), and
> ignores `allowMajorUpdates`. So plugin proposals are reconciled in `report.py`/`version.py`:
> non-upgrades (downgrades) are dropped, `--level` is enforced (the goal does report intermediate
> same-major versions, so e.g. `-l minor` yields `2.22.0 -> 2.22.2` rather than a `3.x` bump), and the
> highest in-range upgrade is kept. Dependencies and properties are constrained by the plugin itself.

## Library API

The pieces are importable and unit-testable without Maven:

```python
from mvn_updates.dependabot import convert_text          # dependabot YAML -> ruleset XML
from mvn_updates.parse import parse_log_text, scan_project
from mvn_updates.report import render_unique, render_modules
from mvn_updates.maven import build_goals, run            # subprocess wrapper
```

## Project layout

```
src/mvn_updates/
  cli.py         # argparse + orchestration (run maven, parse, write reports)
  maven.py       # build goals, allow-flags, run mvn via subprocess
  dependabot.py  # dependabot.yml -> versions ruleset (PyYAML optional, builtin fallback)
  ignores.py     # built-in stable-only ignore patterns (+ custom regex helper)
  parse.py       # parse captured maven output -> Update records; scan poms
  version.py     # Maven-style version comparison (filters downgrades, picks highest)
  report.py      # render the two output files
tests/
  test_dependabot.py, test_parse.py
  data/sample-maven.log          # captured plugin output (offline parsing tests)
  fixtures/multimodule/          # small multi-module Maven project + dependabot.yml
```

## Development

```bash
pip install -e .[dev]
pytest                 # offline: parsing, dependabot conversion, report rendering

# end-to-end against the bundled fixture (needs Maven + network)
mvn-updates -p tests/fixtures/multimodule -o /tmp/out.txt -l minor \
            -d tests/fixtures/multimodule/.github/dependabot.yml
```
