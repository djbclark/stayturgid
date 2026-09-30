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

# Run native-agent unit tests.
kt-test: _kt-sdk
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
kt-build-debug: _kt-sdk
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew assembleDebug

# Assemble release APK (signed).
kt-build-release: _kt-sdk
    cd {{_agent_dir}} && JAVA_HOME={{_java_home}} ./gradlew assembleRelease
