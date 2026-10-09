// Настройки сборки Android-приложения «ДИПСИК ХУДОЖНИК».
// Общий Python-движок лежит в ../python и подключается плагином Chaquopy,
// поэтому ПК-версия и приложение используют один и тот же код.
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
    }
}

rootProject.name = "DipseekArtist"
include(":app")
