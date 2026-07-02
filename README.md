# depcrepit

**How *dep*crepit is your build?** Point it at a multi-module Maven project and get every available
dependency update as one clean, de-duplicated list.

*(decrepit, adj.: worn out or ruined because of age. Like that `junit 4.12` you're still shipping.)*

`depcrepit` runs the [`versions-maven-plugin`](https://www.mojohaus.org/versions/) for you and turns
its noisy, per-module, often-duplicated output into two tidy text files you can actually read, diff, or
paste into a ticket. It understands your `dependabot.yml`, ignores pre-releases and vendor forks by
default, and needs **no Python dependencies** — just Maven on your `PATH`.

```bash
depcrepit -p /path/to/project
# → maven-updates.txt          (one de-duplicated list for the whole project)
# → maven-updates-modules.txt  (per-module breakdown, parent-managed deps extracted)
```

## Why use it

Running `versions:display-dependency-updates` across a big multi-module build gives you the same
update repeated in every module, plugin "updates" that are actually downgrades, and a flood of
`alpha`/`rc`/vendor-fork candidates you'll never ship. `depcrepit` fixes all of that:

- **One list, no duplicates** — a dependency used by 20 modules shows up once.
- **Parent-managed deps extracted** — anything governed by `dependencyManagement`,
  `pluginManagement`, or a version `<property>` is listed once under the parent, not repeated per
  child module.
- **Stable by default** — `alpha`/`beta`/`milestone`/`rc`/`snapshot`/`preview`/… and vendor
  redistribution forks (`-atlassian-1`, `-redhat-00001`, …) are filtered out, so you see the latest
  *real* release. (GA markers like `.Final`/`.RELEASE` and build metadata like `-jre` are kept.)
- **Direct vs. transitive at a glance** — every dependency row is annotated `[direct]` or
  `[via <root dependency>]`, so you instantly know whether you own the update or it rides in
  through something else:
  ```
  junit:junit                 4.12 -> 4.13.2  [direct]
  org.hamcrest:hamcrest-core   1.3 -> 3.0     [via junit:junit]
  ```
- **BOM-import aware** — a framework BOM (`<type>pom</type><scope>import</scope>`) is reported as
  its own single `[bom import]` update instead of being exploded into the dozens of artifacts it
  manages:
  ```
  com.fasterxml.jackson:jackson-bom  2.13.0 -> 2.22.0  [bom import]
  ```
- **Bump-level filtering** — limit the whole report to `major`, `minor`, or `bugfix` upgrades.
- **Dependabot-aware** — point it at your `dependabot.yml` and its `ignore` rules are honoured.
- **Plugin proposals cleaned up** — downgrades dropped, your `--level` enforced, highest in-range
  upgrade kept.
- **Zero install friction** — pure standard library; the only requirement is Maven.

## Install

```bash
pip install .            # from a clone / source checkout
```

Or run it straight from the source tree without installing:

```bash
python -m depcrepit --help
```

**Requirements:** Python ≥ 3.8 and **Maven (`mvn`) on your `PATH`**. `PyYAML` is optional
(`pip install .[yaml]`) and makes Dependabot parsing more robust — a built-in fallback parser is used
when it's absent.

## Quick start

```bash
# Everything available, stable + canonical upstream only (the default)
depcrepit -p .

# Only minor/bugfix upgrades, honouring your Dependabot ignores, into a custom path
depcrepit -p . -o reports/updates.txt -l minor -d .github/dependabot.yml
```

Progress is printed to **stderr**; the report itself goes **only to the files**, which are
overwritten on every run.

## The two reports

| File | What's in it |
|---------------------------|--------------------------------------------------------------------|
| `<output>.txt`            | Every available update across all modules, merged and de-duplicated, grouped into **Dependencies**, **Plugins**, **Properties**. |
| `<output>-modules.txt`    | Per-module breakdown. Parent-managed updates are listed once under the parent; each child shows only its own non-managed updates. Modules with nothing of their own are omitted. |

## Options

| Option                   | Description |
|--------------------------|-------------------------------------------------------------------|
| `-p, --project DIR`      | Maven project root (default `.`). |
| `-o, --output FILE`      | Base output path (default `maven-updates.txt`); the per-module file is `<base>-modules.txt`. |
| `-l, --level LEVEL`      | Allowed bump level: `major` \| `minor` \| `bugfix` (default `major`). |
| `-d, --dependabot FILE`  | A `dependabot.yml` to convert into a versions ruleset. |
| `--allow-prereleases`    | Include non-stable versions (off by default). |
| `--allow-vendor-forks`   | Include third-party redistribution forks like `-atlassian-1`, `-redhat-00001` (off by default). |
| `--ignore-version REGEX` | Full-match regex of versions to ignore (repeatable), e.g. `--ignore-version '(?i).*mycorp.*'`. |
| `-w, --line-width N`     | Output line width; clamped to a minimum of **120** (default `120`). |
| `--no-plugins`           | Skip plugin updates. |
| `--no-properties`        | Skip Maven version-property updates. |
| `--no-origins`           | Skip the extra `dependency:tree` run that annotates each dependency as `[direct]` or `[via <root dependency>]`. |
| `--plugin-version V`     | `versions-maven-plugin` version (default `2.18.0`). |
| `--mvn PATH`             | Path to the `mvn` executable (default `mvn`). |
| `-V, --version`          | Print version. |

## Working with Dependabot

Already curating updates with `dependabot.yml`? Reuse those rules instead of duplicating them. For
each `package-ecosystem: maven` block, the **version constraints** of the `ignore` entries are
converted into a versions ruleset (passed via `-Dmaven.version.rules`):

| Dependabot entry                                                | Converted to |
|----------------------------------------------------------------|--------------|
| `dependency-name` + `versions: [">=X"]` / `["<X"]` …           | `<ignoreVersion type="range">[X,)</…>` etc. |
| `dependency-name` + `versions: ["X.x"]` / `["X.*"]`            | `<ignoreVersion type="regex">X\..*</…>` |
| `dependency-name` + `versions: ["X"]` (exact)                  | `<ignoreVersion type="exact">X</…>` |
| `dependency-name` **alone** / `versions: ["*"]`               | ignore **all** versions of that dependency |
| `dependency-name: "*"` + `versions`                            | top-level (global) `<ignoreVersions>` |

To block a whole group, list the name with no version constraint (Dependabot's own "block this
dependency" form):

```yaml
ignore:
  - dependency-name: "com.example.internal:*"   # never report updates for this group
```

**Wildcards** in `dependency-name` (`org.slf4j:*`, `org.springframework.*`) are passed through
natively. `update-types` are **ignored** — use `-l/--level` for a project-wide limit. Entries without
a `versions` constraint are skipped.

## Filtering pre-releases and vendor forks

By default `depcrepit` reports the latest **stable, canonical** version. Turn the filters off or add
your own:

```bash
depcrepit -p .                          # stable + canonical upstream only (default)
depcrepit -p . --allow-prereleases      # include alpha/beta/milestone/rc/...
depcrepit -p . --allow-vendor-forks     # include -atlassian/-redhat/... forks
depcrepit -p . --ignore-version '(?i).*mycorp.*'   # ignore one more fork/qualifier
```

This works by adding global `<ignoreVersions>` regex rules so the **plugin** skips those candidates
and resolves the newest acceptable one — it is *not* a post-filter (which would wrongly hide a
dependency whose only candidate happened to be a pre-release). GA qualifiers like `.Final`,
`.RELEASE`, `.GA` and build metadata like `-jre` are deliberately kept; what makes
`5.6.15.Final-atlassian-4` "unofficial" is the vendor `-atlassian` suffix. All of this combines with
`-d/--dependabot`.

> **A note on plugin proposals.** `display-plugin-updates` groups proposals by the Maven version they
> require, can list a version *lower* than the one in use (`3.8.0 -> 3.6.0`), and ignores
> `allowMajorUpdates`. `depcrepit` reconciles this: downgrades are dropped, `--level` is enforced,
> and the highest in-range upgrade is kept.

## Library API

The internals are importable and unit-testable without Maven:

```python
from depcrepit.dependabot import convert_text          # dependabot YAML -> ruleset XML
from depcrepit.deptree import parse_tree_text           # dependency:tree -> direct/transitive
from depcrepit.parse import parse_log_text, scan_project
from depcrepit.report import render_unique, render_modules
from depcrepit.maven import build_goals, run, run_tree   # subprocess wrappers
```

## Development

```bash
pip install -e .[dev]
pytest                 # offline: parsing, dependabot conversion, report rendering

# end-to-end against the bundled fixture (needs Maven + network)
depcrepit -p tests/fixtures/multimodule -o /tmp/out.txt -l minor \
            -d tests/fixtures/multimodule/.github/dependabot.yml
```

## Author

Built and maintained by **Kelemen Balint**.

- GitHub: [@kdlogen](https://github.com/kdlogen)
- Repository: [github.com/kdlogen/depcrepit](https://github.com/kdlogen/depcrepit)
- Issues & feature requests: [github.com/kdlogen/depcrepit/issues](https://github.com/kdlogen/depcrepit/issues)
- Email: [kelemenf.balint@gmail.com](mailto:kelemenf.balint@gmail.com)

Stars, issues, and pull requests are all welcome. ⭐

## License

[WTFPL](LICENSE) — Do What The Fuck You Want To Public License. Free software, forever. Use it,
fork it, sell it, rename your cat after it. No strings attached.
</content>
</invoke>
