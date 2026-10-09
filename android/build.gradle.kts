// Версии подобраны совместимой связкой:
//   Gradle 8.11.1  <-  AGP 8.9.3  <-  Kotlin 2.0.21 + Compose Compiler 2.0.21
//   Chaquopy 17.0.0 поддерживает AGP 7.3.x..9.2.x
//
// AGP именно 8.9.x, а не 8.7.x: на 8.7 сборка с Chaquopy падает на
// :app:compileDebugKotlin с "does not hold the state lock for root project"
// (chaquo/chaquopy#1339: помогло обновление AGP до 8.9).
plugins {
    id("com.android.application") version "8.9.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
