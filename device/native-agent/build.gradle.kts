plugins {
    id("com.android.application") version "8.10.0" apply false
    id("org.jetbrains.kotlin.android") version "2.1.21" apply false
    id("com.diffplug.spotless") version "7.0.4"
    id("io.gitlab.arturbosch.detekt") version "1.23.8" apply false
    id("org.jetbrains.kotlinx.kover") version "0.9.9" apply false
}

// ── Spotless (formatting) ──────────────────────────────────────────────
// Wraps ktfmt (Meta) for deterministic, opinionated Kotlin formatting.
// kotlinlangStyle = 4-space indent, matching the project's existing conventions.
// Run:  ./gradlew spotlessCheck   (CI / pre-commit)
//       ./gradlew spotlessApply   (auto-fix)
spotless {
    kotlin {
        target("app/src/**/*.kt")
        targetExclude("**/build/**", "**/generated/**")
        ktfmt("0.54").kotlinlangStyle()
    }
    kotlinGradle {
        target("**/*.gradle.kts")
        targetExclude("**/build/**")
        ktfmt("0.54").kotlinlangStyle()
    }
}
