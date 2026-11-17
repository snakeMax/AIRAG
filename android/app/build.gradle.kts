// The Android app is a thin shell: Chaquopy runs the same Python code (../../airag)
// and web UI (../../web) as the desktop app, and a WebView shows it.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val repoRoot = rootDir.parentFile
val appVersion: String = Regex("""__version__\s*=\s*"([^"]+)"""")
    .find(repoRoot.resolve("airag/__init__.py").readText())!!.groupValues[1]
val versionParts = appVersion.split(".").map { it.takeWhile(Char::isDigit).toIntOrNull() ?: 0 } + listOf(0, 0, 0)

android {
    namespace = "io.github.snakemax.airag"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.snakemax.airag"
        minSdk = 26
        targetSdk = 35
        versionName = appVersion
        versionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    // Release signing comes from environment variables (GitHub secrets in CI).
    // Without them the release build is signed with the debug key, which is fine for local testing.
    val ks = System.getenv("AIRAG_KEYSTORE_FILE")
    signingConfigs {
        if (ks != null && file(ks).exists()) {
            create("release") {
                storeFile = file(ks)
                storePassword = System.getenv("AIRAG_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("AIRAG_KEY_ALIAS")
                keyPassword = System.getenv("AIRAG_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

// Copy the shared Python package, with the web UI inside it, into the build folder.
val pythonSrc: File = layout.buildDirectory.dir("python-src").get().asFile
val syncPython by tasks.registering(Sync::class) {
    from(repoRoot.resolve("airag")) {
        into("airag")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    from(repoRoot.resolve("web")) { into("airag/web") }
    into(pythonSrc)
}
tasks.named("preBuild") { dependsOn(syncPython) }
// Chaquopy's own tasks read that folder, so they must run after the copy
tasks.matching { it.name.contains("Python") && it.name != "syncPython" }.configureEach { dependsOn(syncPython) }

chaquopy {
    defaultConfig {
        version = "3.12"
        System.getenv("AIRAG_BUILD_PYTHON")?.let { buildPython(it) }
        pip { install("-r", repoRoot.resolve("requirements-android.txt").absolutePath) }
        extractPackages("airag", "certifi")
        pyc { src = true }
    }
    sourceSets {
        getByName("main") { srcDir(pythonSrc) }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.12.1")
}
