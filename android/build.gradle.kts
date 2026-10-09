// Версии подобраны совместимой связкой:
//   Gradle 8.9  <-  AGP 8.7.3  <-  Kotlin 2.0.21 + Compose Compiler 2.0.21
//   Chaquopy 17.0.0 поддерживает AGP 7.3.x..9.2.x
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
