import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Every codec ships by default: without the graphics bindings engine_preflight refuses to patch.
// -PfullCodecs=false builds the minimal diagnostic baseline instead.
val fullCodecs = findProperty("fullCodecs")?.toString()?.let { it.isEmpty() || it.toBoolean() } ?: true

val engineAssets = layout.buildDirectory.dir("generated/engine-assets")
val stageEngineAssets by tasks.registering(Sync::class) {
    into(engineAssets)
    // AAPT otherwise decompresses .gz assets and strips their suffix, changing consumed bytes.
    from("../../resources/runtime") {
        into("engine/runtime")
        exclude("**/*.pyd", "**/*.dll", "**/*.exe")
        rename { "$it.payload" }
    }
    from("../../resources/catalog") { into("engine/catalog"); rename { "$it.payload" } }
    // Indonesian borrows every texture payload it does not re-draw from catalog/ beside it.
    from("../../resources/catalog_id") { into("engine/catalog_id"); rename { "$it.payload" } }
    from("../../tools") {
        into("engine/tools")
        include("*.py")
        // Research and Tencent's Windows builder are never shipped on Android.
        exclude("qts_builder.py")
        rename { "$it.payload" }
    }
    from("../../app") {
        into("engine/tools")
        include("apk_tools.py")
        rename { "$it.payload" }
    }
    from("../../resources/key") {
        into("engine/key")
        include("key.pk8", "cert.der")
        rename { "$it.payload" }
    }
    from("../native/licenses") { into("engine/notices"); rename { "$it.payload" } }
    doLast {
        val root = engineAssets.get().asFile.resolve("engine")
        val hashes = sortedMapOf<String, String>()
        root.walkTopDown().filter { it.isFile && it.name != "manifest.json" }.forEach { file ->
            val hash = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { stream ->
                val bytes = ByteArray(1024 * 1024)
                while (true) {
                    val count = stream.read(bytes)
                    if (count < 0) break
                    hash.update(bytes, 0, count)
                }
            }
            hashes[file.relativeTo(root).invariantSeparatorsPath.removeSuffix(".payload")] =
                hash.digest().joinToString("") { "%02x".format(it) }
        }
        root.resolve("manifest.json").writeText(groovy.json.JsonOutput.toJson(mapOf("files" to hashes)))
    }
}

android {
    namespace = "dev.halixm.hokacepatcher"
    compileSdk = 35
    defaultConfig {
        applicationId = "dev.halixm.hokacepatcher"
        minSdk = 30
        targetSdk = 35
        versionCode = 1
        versionName = "0.1-feasibility"
        ndk { abiFilters += "arm64-v8a" }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildFeatures { aidl = true; buildConfig = true }
    // The runtime contains Python packages such as _backends; AAPT's default skips these directories.
    androidResources { ignoreAssetsPattern = "" }
    sourceSets.getByName("main").assets.srcDir(engineAssets)
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
tasks.named("preBuild") { dependsOn(stageEngineAssets) }

chaquopy {
    defaultConfig {
        version = "3.12"
        extractPackages("archspec")
        buildPython("../../.venv/Scripts/python.exe")
        pip {
            // These Android wheels differ from desktop pins: prove fixture parity before release.
            if (fullCodecs) {
                install(rootProject.file("wheels/lz4-4.3.2-cp312-cp312-android_24_arm64_v8a.whl").absolutePath)
                install(rootProject.file("wheels/zstandard-0.22.0-cp312-cp312-android_24_arm64_v8a.whl").absolutePath)
            } else {
                install("lz4==4.3.2")
                install("zstandard==0.22.0")
            }
            install("pypinyin==0.55.0")
            install("archspec==0.2.6")
            // Graphics bindings are a measured gate, not silently replaced by text-only support.
            if (fullCodecs) {
                options("--find-links", rootProject.file("wheels").absolutePath)
                install("astc-encoder-py==0.1.12")
                install("texture2ddecoder==1.0.6")
                install("pyooz==0.0.8")
                install(rootProject.file("wheels/chaquopy_freetype-2.9.1-cp312-cp312-android_24_arm64_v8a.whl").absolutePath)
                install("pillow==11.0.0")
            }
        }
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}

// Resolved runtime candidates, including annotation-only dependencies: an audit, not a claim
// that every resolved class survives APK packaging or that its license review is complete.
tasks.register("writeRuntimeDependencyInventory") {
    doLast {
        val artifacts = configurations.getByName("releaseRuntimeClasspath").resolvedConfiguration.resolvedArtifacts
        val records = artifacts.map { artifact ->
            val id = artifact.moduleVersion.id
            val digest = MessageDigest.getInstance("SHA-256")
            artifact.file.inputStream().use { stream ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = stream.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
            }
            mapOf("coordinate" to "${id.group}:${id.name}:${id.version}",
                "artifact" to artifact.file.name, "bytes" to artifact.file.length(),
                "sha256" to digest.digest().joinToString("") { "%02x".format(it) })
        }.sortedBy { it["coordinate"].toString() }
        val target = layout.buildDirectory.file("reports/release-runtime-dependencies.json").get().asFile
        target.parentFile.mkdirs()
        target.writeText(groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(
            mapOf("schema" to 1, "scope" to "Resolved release runtime classpath; packaging and notice review remain separate.",
                "components" to records))))
        println("Recorded ${records.size} resolved release runtime artifacts: $target")
    }
}
