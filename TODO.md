# Roadmap

## Gradle support

The report/version/origin layers (`report.py`, `version.py`, `deptree.Origin`, the Dependabot rule
model) are build-tool-agnostic; only the collection side is Maven-specific. Gradle support means a
second collection backend.

**Key insight:** the de-facto standard for Gradle update checking is the
[ben-manes gradle-versions-plugin](https://github.com/ben-manes/gradle-versions-plugin)
(`dependencyUpdates` task). It normally has to be declared in the project's build script, but an
**init script** injects it without touching the analyzed project — preserving depcrepit's core
property (point it at any project, change nothing, get a report):

```bash
gradle --init-script <generated>.init.gradle dependencyUpdates -DoutputFormatter=json
```

The plugin emits JSON per module, so no log parsing is needed on the Gradle side.

### Phase 0 — backend abstraction (no behavior change)

- [ ] `backends/base.py`: `Backend` protocol — `detect(dir)`, `collect_updates(...) -> List[Update]`,
      `collect_origins(...) -> ModuleOrigins`, `scan(...) -> (parents, managed, boms)`
- [ ] `backends/maven.py`: move Maven orchestration (runner + pom scan + log parse) behind it
- [ ] CLI: `--build-tool auto|maven|gradle`; auto-detect `pom.xml` vs `settings.gradle(.kts)`
- [ ] All existing tests stay green

### Phase 1 — Gradle updates (core value)

- [ ] `backends/gradle/init_script.py`: generate the init script; translate the three filter sources
      into `rejectVersionIf { ... }`:
      stable-only / vendor-fork regexes (reuse `ignores.py`), `--level` caps (the closure receives
      `current` + `candidate`, so major/minor limits compile to a component comparison),
      `--ignore-version` regexes
- [ ] `backends/gradle/runner.py`: prefer `./gradlew`, fall back to `gradle` (mirror `--mvn` with
      `--gradle`)
- [ ] `backends/gradle/parse.py`: `build/dependencyUpdates/report.json` per module -> `Update`
- [ ] Fixture: small multi-project Gradle build mirroring the Maven fixture; offline tests parse
      captured JSON

### Phase 2 — feature parity

| Maven concept                 | Gradle equivalent                                  | Approach |
|-------------------------------|----------------------------------------------------|----------|
| `dependency:tree` origins     | `:module:dependencies` task                        | Parse the `+---`/`\---` tree (same model as `deptree.py`, different indent unit) -> `[direct]` / `[via ...]` |
| Parent `dependencyManagement` | `platform(...)` / version catalog                  | `platform()` deps -> `[bom import]`; catalog-managed -> "managed" |
| Version `<properties>`        | `gradle.properties` + `libs.versions.toml` `[versions]` | Properties section |
| Plugin updates                | `plugins {}` / catalog plugin versions             | The versions plugin already reports them -> Plugins section |

### Phase 3 — Dependabot + version catalogs

- [ ] `package-ecosystem: "gradle"` ignore blocks -> `rejectVersionIf` (reuse the rule model; only
      the emitter differs: XML ruleset vs Groovy closure)
- [ ] First-class `gradle/libs.versions.toml` support (how modern Gradle projects pin everything)

### Risks / notes

- The init script resolves the versions plugin from the Gradle Plugin Portal at runtime (network
  needed — same as Maven resolving the versions plugin).
- Realistic compatibility floor: Gradle ~6.8+.
- Fixture should mix `java-library` + `application`; Android is out of scope initially.
