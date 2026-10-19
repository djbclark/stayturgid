# Kotlin tooling recipes for the native-agent Android app.
# ──────────────────────────────────────────────────────────────────────
# Usage: just kt-check          (all checks, same as CI)
#        just kt-format          (auto-fix formatting)
#        just kt-detekt          (static analysis only)
#        just kt-detekt-baseline (snapshot existing issues)
#        just kt-test            (unit tests)

_agent_dir := "device/native-agent"

# Gradle 8.x needs JDK 17–21; auto-detect a compatible JDK.
_java_home := if path_exists("/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home") == "true" {
    "/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
} else if path_exists("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home") == "true" {
    "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
} else {
    env_var_or_default("JAVA_HOME", "")
}

# Run all Kotlin checks (formatting + static analysis + tests).
kt-check: kt-format-check kt-detekt kt-test

# Check Kotlin formatting (Spotless + ktfmt). Fails if anything is unformatted.
kt-format-check:
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew spotlessCheck

# Auto-fix Kotlin formatting. Safe to run at any time.
kt-format:
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew spotlessApply

# Run detekt static analysis.
kt-detekt:
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew detekt

# Snapshot all current detekt issues into baseline.xml (for gradual adoption).
kt-detekt-baseline:
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew detektBaseline
    @echo "Baseline written to {{_agent_dir}}/config/detekt/baseline.xml"

# Generate the full default detekt.yml for reference.
kt-detekt-generate-config:
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew detektGenerateConfig
    @echo "Full default config written to {{_agent_dir}}/config/detekt/detekt.yml"
    @echo "(Your custom overrides are merged via buildUponDefaultConfig = true)"

# stayturgid-agent is built and tested only on GitHub CI (free runners), never on this Mac
# (djbclark, 2026-10-17 Forgejo, 2026-10-18 GitHub): push master to origin, `just agent-ci-run`,
# then `just agent-ci-fetch`. Formatting and detekt (above) stay local; they are what the
# pre-commit hooks run.
_kt-ci-only:
    #!/usr/bin/env bash
    if [[ "${STAYTURGID_LOCAL_GRADLE:-0}" != 1 ]]; then
      echo "stayturgid-agent builds and tests run on GitHub CI only (github.com/djbclark/stayturgid, ci/base)." >&2
      echo "Push: git -C {{ repo }} push origin master; then: just agent-ci-run; then: just agent-ci-fetch" >&2
      echo "See device/native-agent/README.md, Build." >&2
      exit 3
    fi

# Run the GitHub CI Android build of REF (default origin/master): overlay ci/base, push ci/run/agent-<slug>, print the run URL.
agent-ci-run ref="origin/master":
    #!/usr/bin/env bash
    set -euo pipefail
    git -C "{{ repo }}" fetch origin ci/base master
    tmp="$(mktemp -t github-ci-run.XXXXXX)"
    git -C "{{ repo }}" show origin/ci/base:scripts/github-ci-run > "$tmp"
    cd "{{ repo }}" && bash "$tmp" --no-wait --agent "{{ ref }}"

# Fetch the CI-built APK for HEAD (or SHA) from GitHub releases and sign it with the release key.
agent-ci-fetch sha="":
    python3 "{{ repo }}/control/tools/native-agent/ci_fetch_sign.py" {{ sha }}

# Run native-agent unit tests (GitHub CI only; see _kt-ci-only).
kt-test: _kt-ci-only _kt-sdk
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew test

# Install the compileSdk platform into the SDK local.properties points at, if
# missing (a disk cleanup removed it 2026-09-29 and every build failed).
_kt-sdk:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{_agent_dir}}"
    sdk="$(sed -n 's/^sdk.dir=//p' local.properties 2>/dev/null)"
    sdk="${sdk:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
    api="$(sed -n 's/^ *compileSdk = \([0-9]*\).*/\1/p' app/build.gradle.kts)"
    if [[ -n "$api" && ! -d "$sdk/platforms/android-$api" ]]; then
      echo "Installing platforms;android-$api into $sdk"
      yes | sdkmanager --sdk_root="$sdk" "platforms;android-$api" >/dev/null
    fi

# Assemble debug APK.
kt-build-debug: _kt-ci-only _kt-sdk
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew assembleDebug

# Assemble release APK (signed; GitHub CI only, see _kt-ci-only and agent-ci-fetch).
kt-build-release: _kt-ci-only _kt-sdk
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew assembleRelease
