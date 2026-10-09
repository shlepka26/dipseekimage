plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

// Переопределяется из командной строки, без правки файла:
//   gradle -Pdip.python="C:/Python312/python.exe" -Pdip.abis=arm64-v8a,x86_64 :app:assembleDebug
// Значения по умолчанию рассчитаны на CI: там Python 3.12 ставит setup-python,
// а вторая архитектура не нужна.
val dipPython: String? = (findProperty("dip.python") as String?)?.takeIf { it.isNotBlank() }
val dipAbis: List<String> = ((findProperty("dip.abis") as String?) ?: "arm64-v8a")
    .split(",").map { it.trim() }.filter { it.isNotEmpty() }

android {
    namespace = "com.dipseek.artist"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.dipseek.artist"
        // minSdk 24 — жёсткое требование: wheel pillow-11.0.0 собран под android_24,
        // на меньшем API pip не найдёт подходящий файл.
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        ndk {
            // arm64-v8a покрывает все современные телефоны и даёт самый маленький APK.
            // Для запуска на эмуляторе: -Pdip.abis=arm64-v8a,x86_64
            abiFilters += dipAbis
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    packaging {
        resources.excludes += setOf(
            "/META-INF/{AL2.0,LGPL2.1}",
            "META-INF/DEPENDENCIES",
            "META-INF/LICENSE*",
            "META-INF/NOTICE*",
        )
    }
}

chaquopy {
    defaultConfig {
        // Версия Python приложения. 3.12 выбрана потому, что именно для неё
        // в репозитории Chaquopy есть готовые wheels numpy и pillow.
        version = "3.12"

        // На сборочной машине нужен Python 3.12 (Chaquopy компилирует байткод
        // и собирает колёса). Если путь не задан явно, Chaquopy ищет сам по
        // правилам своей платформы: на Linux/macOS python3.12 -> python3,
        // на Windows py -3.12 -> py -3 -> python. Это надёжнее, чем жёстко
        // прописать "python3": такая строка на Windows не существует.
        // build-apk.ps1 передаёт путь явно: -Pdip.python="C:/Python312/python.exe"
        if (dipPython != null) buildPython(dipPython)

        pip {
            // Версии прибиты гвоздями: это ровно те wheels, что лежат в
            // репозитории Chaquopy для Python 3.12 и arm64-v8a.
            install("numpy==1.26.2")     // numpy-1.26.2-0-cp312-cp312-android_21_arm64_v8a.whl
            install("pillow==11.0.0")    // pillow-11.0.0-0-cp312-cp312-android_24_arm64_v8a.whl
        }

        pyc {
            src = true                  // исходники компилируются в .pyc
        }
    }

    sourceSets {
        getByName("main") {
            // Общий движок: и ПК-версия, и приложение берут код отсюда.
            // Путь считается от android/app, то есть это <корень проекта>/python.
            srcDir("../../python")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")

    // Шифрованное хранилище для ключа DeepSeek: ключ не должен лежать
    // в APK и не должен читаться из открытого файла настроек.
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
}
