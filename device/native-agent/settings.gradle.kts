pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        mavenLocal()
    }
}

// Prefer property override for CI/worktrees; never rely on shell ~ expansion.
val defaultShizuku = file("${System.getenv("HOME") ?: ""}/src/Shizuku/api")

val shizukuApiDir: File =
    when {
        providers.gradleProperty("shizuku.api.dir").isPresent ->
            file(providers.gradleProperty("shizuku.api.dir").get())
        !providers.environmentVariable("SHIZUKU_API_DIR").orNull.isNullOrBlank() ->
            file(providers.environmentVariable("SHIZUKU_API_DIR").get())
        else -> defaultShizuku
    }

val compositeProp = providers.gradleProperty("shizuku.composite").orNull
val useCompositeShizuku: Boolean =
    when (compositeProp) {
        "false" -> false
        "true" -> true
        // Opt-in only (-Pshizuku.composite=true). Auto-enabling whenever
        // ~/src/Shizuku/api existed broke every release build and the Kotlin
        // pre-commit hooks once that checkout moved to AGP 9.2.1 / Gradle 9.4.1
        // (2026-09-29); the app pins dev.rikka.shizuku:api from Maven anyway.
        else -> false
    }

if (useCompositeShizuku) {
    if (!shizukuApiDir.isDirectory) {
        throw GradleException(
            "Shizuku API dir missing: $shizukuApiDir " +
                "(set -Pshizuku.api.dir= or SHIZUKU_API_DIR, or -Pshizuku.composite=false for Maven)"
        )
    }
    includeBuild(shizukuApiDir) {
        dependencySubstitution {
            substitute(module("dev.rikka.shizuku:api")).using(project(":api"))
            substitute(module("dev.rikka.shizuku:provider")).using(project(":provider"))
        }
    }
    println("stayturgid-agent: composite Shizuku API from $shizukuApiDir")
} else {
    println("stayturgid-agent: using published/Maven Shizuku (composite disabled)")
}

rootProject.name = "stayturgid-agent"

include(":app")
