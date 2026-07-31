import java.time.Instant
import java.time.temporal.ChronoUnit

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("io.gitlab.arturbosch.detekt")
    id("org.jetbrains.kotlinx.kover")
}

android {
    namespace = "org.stayturgid.agent"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.stayturgid.agent"
        minSdk = 26
        targetSdk = 36
        versionCode = 18
        versionName = "0.9.0-new-icon"
        val buildTimeUtc =
            System.getenv("SOURCE_DATE_EPOCH")?.toLongOrNull()?.let { Instant.ofEpochSecond(it) }
                ?: Instant.now().truncatedTo(ChronoUnit.SECONDS)
        val repoRoot = rootProject.projectDir.resolve("../..").canonicalPath
        val revision =
            providers
                .exec {
                    commandLine("git", "-C", repoRoot, "rev-parse", "--short=12", "HEAD")
                    isIgnoreExitValue = true
                }
                .standardOutput
                .asText
                .get()
                .trim()
                .ifEmpty { "unknown" }
        val treeState =
            providers
                .exec {
                    commandLine(
                        "git",
                        "-C",
                        repoRoot,
                        "status",
                        "--porcelain",
                        "--untracked-files=no",
                    )
                    isIgnoreExitValue = true
                }
                .standardOutput
                .asText
                .get()
                .trim()
                .let { if (it.isEmpty()) "clean" else "dirty" }
        buildConfigField("String", "BUILD_TIME_UTC", "\"$buildTimeUtc\"")
        buildConfigField("String", "BUILD_REVISION", "\"$revision\"")
        buildConfigField("String", "BUILD_TREE_STATE", "\"$treeState\"")
    }

    buildFeatures {
        buildConfig = true
        aidl = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }

    testOptions { unitTests.all { it.useJUnitPlatform() } }

    signingConfigs {
        create("release") {
            storeFile = file("../agent-release.jks")
            storePassword = "stayturgid"
            keyAlias = "agent"
            keyPassword = "stayturgid"
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = signingConfigs.getByName("release")
        }
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            // BouncyCastle (bcpkix/bcutil/bcprov) + jspecify ship duplicate
            // multi-release metadata that the resource merger rejects.
            excludes += "/META-INF/versions/9/OSGI-INF/MANIFEST.MF"
            excludes += "/META-INF/versions/**/module-info.class"
        }
    }
}

// ── detekt (static analysis) ───────────────────────────────────────────
// Run:  ./gradlew detekt          (analysis with type resolution)
//       ./gradlew detektBaseline  (snapshot existing issues for gradual adoption)
detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom(files("$rootDir/config/detekt/detekt.yml"))
    baseline = file("$rootDir/config/detekt/baseline.xml")
}

dependencies {
    // Coordinates substituted to ~/src/Shizuku/api when composite build is on.
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.annotation:annotation:1.9.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    // Embedded ADB client (peer-start of Shizuku on Fire OS over external ADB —
    // issue #61). BouncyCastle builds the X.509 client cert for the A_STLS path;
    // matches the version used by the Shizuku fork's manager module.
    implementation("org.bouncycastle:bcpkix-jdk18on:1.80")

    // detekt formatting rules (wraps ktlint for analysis-only checks beyond
    // what ktfmt handles — import ordering, trailing commas, etc.).
    detektPlugins("io.gitlab.arturbosch.detekt:detekt-formatting:1.23.8")

    // Modern Kotlin unit testing stack (2026)
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testImplementation("io.kotest:kotest-assertions-core:6.2.2")
    testImplementation("io.mockk:mockk-android:1.14.11")
    testImplementation("app.cash.turbine:turbine:1.2.1")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")

    // Konsist: architectural consistency as unit tests.
    // Write tests like "all classes ending with 'Receiver' must extend BroadcastReceiver".
    testImplementation("com.lemonappdev:konsist:0.17.3")
}
