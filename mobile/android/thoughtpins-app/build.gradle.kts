import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.thoughtpins.app"
    compileSdk = 37

    defaultConfig {
        val googleServerClientId = providers.gradleProperty("THOUGHTPINS_GOOGLE_SERVER_CLIENT_ID").orElse("").get()
        applicationId = "com.thoughtpins.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "THOUGHTPINS_API_BASE_URL", "\"https://api.thoughtpins.com\"")
        buildConfigField("String", "GOOGLE_SERVER_CLIENT_ID", "\"$googleServerClientId\"")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // Upload signing, supplied by the release host and never by this repository.
    //
    // Values come from a gitignored keystore.properties beside this file, or from
    // the environment so CI can inject them. The config is only registered when
    // the material is actually present: an unsigned release build is a normal
    // outcome on a developer machine, and failing the build there would mean
    // nobody could run `assembleRelease` to check that R8 has not broken
    // anything. Play rejects an unsigned bundle at upload, which is the right
    // place for that error to surface.
    val keystoreProperties = Properties().apply {
        val file = rootProject.file("thoughtpins-app/keystore.properties")
        if (file.exists()) file.inputStream().use { load(it) }
    }

    fun signingValue(propertyName: String, environmentName: String): String? =
        keystoreProperties.getProperty(propertyName)?.takeIf { it.isNotBlank() }
            ?: System.getenv(environmentName)?.takeIf { it.isNotBlank() }

    val storePath = signingValue("storeFile", "THOUGHTPINS_ANDROID_KEYSTORE")
    val storeSecret = signingValue("storePassword", "THOUGHTPINS_ANDROID_KEYSTORE_PASSWORD")
    val aliasName = signingValue("keyAlias", "THOUGHTPINS_ANDROID_KEY_ALIAS")
    val aliasSecret = signingValue("keyPassword", "THOUGHTPINS_ANDROID_KEY_PASSWORD")
    val releaseSigningAvailable =
        storePath != null && storeSecret != null && aliasName != null && aliasSecret != null &&
            file(storePath).exists()

    signingConfigs {
        if (releaseSigningAvailable) {
            create("release") {
                storeFile = file(storePath!!)
                storePassword = storeSecret
                keyAlias = aliasName
                keyPassword = aliasSecret
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = if (releaseSigningAvailable) signingConfigs.getByName("release") else null
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += setOf("META-INF/AL2.0", "META-INF/LGPL2.1")
    }
}

dependencies {
    implementation(project(":thoughtpins-core"))
    implementation(platform("androidx.compose:compose-bom:2026.06.01"))
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.fragment:fragment-ktx:1.8.9")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0")
    implementation("com.squareup.okhttp3:okhttp:5.4.0")
    implementation("androidx.credentials:credentials:1.6.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.6.0")
    implementation("com.google.android.libraries.identity.googleid:googleid:1.2.0")
}
