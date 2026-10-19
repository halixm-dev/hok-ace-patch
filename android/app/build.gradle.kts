import java.security.MessageDigest

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Every codec ships by default: without the graphics bindings engine_preflight refuses to patch.
// -PfullCodecs=false builds the minimal diagnostic baseline instead.
val fullCodecs = findProperty("fullCodecs")?.toString()?.let { it.isEmpty() || it.toBoolean() } ?: true

val patchVersion = rootProject.file("../VERSION").readText().trim()
val buildVersion = providers.gradleProperty("patchVersionName").orElse(patchVersion).get()
require(Regex("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+").matches(buildVersion)) {
    "Patch version must have three game version numbers plus a revision, for example 1.6.1.1"
}

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
    // This repo's sprite art for the regioned atlases, read from beside the catalogs.
    from("../../resources/sprites") { into("engine/sprites"); rename { "$it.payload" } }
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

// The shared design (DESIGN.md): theme tokens become resources, fonts become res/font, and the
// strings file is a class resource so UiText and JVM unit tests read the same bytes.
val uiResources = layout.buildDirectory.dir("generated/ui-res")
val uiClassResources = layout.buildDirectory.dir("generated/ui-java")
val stageUiResources by tasks.registering {
    val theme = file("../../resources/ui/theme.json")
    val strings = file("../../resources/ui/strings.json")
    val fonts = file("../../resources/fonts")
    inputs.files(theme, strings); inputs.dir(fonts)
    outputs.dirs(uiResources, uiClassResources)
    doLast {
        val res = uiResources.get().asFile.apply { deleteRecursively() }
        val classes = uiClassResources.get().asFile.apply { deleteRecursively() }
        classes.resolve("ui").mkdirs()
        strings.copyTo(classes.resolve("ui/strings.json"))
        fonts.resolve("OFL.txt").copyTo(classes.resolve("ui/fonts/OFL.txt"))
        // Resource names are lower case: Barlow-SemiBold.ttf becomes barlow_semibold.ttf.
        res.resolve("font").mkdirs()
        fonts.listFiles { it: File -> it.extension == "ttf" }!!.forEach {
            it.copyTo(res.resolve("font/" + it.name.lowercase().replace('-', '_')))
        }
        @Suppress("UNCHECKED_CAST")
        val tokens = groovy.json.JsonSlurper().parse(theme) as Map<String, Map<String, Any>>
        fun name(token: String) = token.replace('-', '_')
        fun color(value: String): String {
            val rgba = Regex("rgba\\((\\d+),\\s*(\\d+),\\s*(\\d+),\\s*([0-9.]+)\\)").matchEntire(value)
                ?: return "#FF" + value.removePrefix("#")
            val (r, g, b, a) = rgba.destructured
            return "#%02X%02X%02X%02X".format(Math.round(a.toFloat() * 255), r.toInt(), g.toInt(), b.toInt())
        }
        fun number(value: Any) = value.toString().removeSuffix("px").removeSuffix("em")
        val lines = mutableListOf<String>()
        tokens.getValue("colors").forEach { (token, value) ->
            lines += "<color name=\"${name(token)}\">${color(value.toString())}</color>"
        }
        tokens.getValue("rounded").forEach { (token, value) ->
            lines += "<dimen name=\"corner_${name(token)}\">${number(value)}dp</dimen>"
        }
        tokens.getValue("spacing").forEach { (token, value) ->
            lines += "<dimen name=\"space_${name(token)}\">${number(value)}dp</dimen>"
        }
        tokens.getValue("typography").forEach { (token, value) ->
            @Suppress("UNCHECKED_CAST") val step = value as Map<String, Any>
            lines += "<dimen name=\"type_${name(token)}\">${number(step.getValue("fontSize"))}sp</dimen>"
            step["letterSpacing"]?.let {
                lines += "<item name=\"type_${name(token)}_tracking\" type=\"dimen\" format=\"float\">${number(it)}</item>"
            }
        }
        res.resolve("values").mkdirs()
        res.resolve("values/theme.xml").writeText(
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!-- Generated from resources/ui/theme.json. -->\n" +
                "<resources>\n" + lines.joinToString("") { "    $it\n" } + "</resources>\n")
    }
}

android {
    namespace = "dev.halixm.hokacepatcher"
    compileSdk = 35
    defaultConfig {
        applicationId = "dev.halixm.hokacepatcher"
        minSdk = 30
        targetSdk = 35
        versionCode = providers.gradleProperty("patchVersionCode").orElse("1").get().toInt()
        versionName = buildVersion
        ndk { abiFilters += "arm64-v8a" }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    // The patcher key lives outside the repo. When the signing variables are set, debug and
    // release builds both sign with it; tools/ci/sign_android.ps1 adds the rotation lineage.
    val releaseStore = providers.environmentVariable("ANDROID_RELEASE_KEYSTORE").orNull
    if (releaseStore != null) {
        signingConfigs.create("privateRelease") {
            storeFile = file(releaseStore)
            storePassword = providers.environmentVariable("ANDROID_RELEASE_STORE_PASSWORD").get()
            keyAlias = providers.environmentVariable("ANDROID_RELEASE_KEY_ALIAS").get()
            keyPassword = providers.environmentVariable("ANDROID_RELEASE_KEY_PASSWORD").get()
        }
        buildTypes.getByName("debug") { signingConfig = signingConfigs.getByName("privateRelease") }
        buildTypes.getByName("release") { signingConfig = signingConfigs.getByName("privateRelease") }
    }
    // Without the variables, debug builds use this PC's SDK debug key and release builds stay unsigned.
    buildFeatures { aidl = true; buildConfig = true }
    // The runtime contains Python packages such as _backends; AAPT's default skips these directories.
    androidResources { ignoreAssetsPattern = "" }
    sourceSets.getByName("main").assets.srcDir(engineAssets)
    sourceSets.getByName("main").res.srcDir(uiResources)
    sourceSets.getByName("main").resources.srcDir(uiClassResources)
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
tasks.named("preBuild") { dependsOn(stageEngineAssets, stageUiResources) }

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
    testImplementation("org.json:json:20180813")
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
