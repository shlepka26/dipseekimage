package com.dipseek.artist

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Настройки приложения.
 *
 * Ключ DeepSeek — единственный секрет, поэтому он лежит в шифрованном
 * хранилище и НИКОГДА не попадает в APK: пользователь вводит свой ключ сам.
 * Если шифрованное хранилище недоступно (сломанный Keystore на редких
 * прошивках), приложение продолжает работать с обычными настройками.
 */
class Prefs(context: Context) {

    private val appContext = context.applicationContext

    private val secure: SharedPreferences by lazy {
        try {
            val masterKey = MasterKey.Builder(appContext)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                appContext,
                "dipseek_secrets",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (t: Throwable) {
            appContext.getSharedPreferences("dipseek_secrets_fallback", Context.MODE_PRIVATE)
        }
    }

    private val plain: SharedPreferences by lazy {
        appContext.getSharedPreferences("dipseek_settings", Context.MODE_PRIVATE)
    }

    var apiKey: String
        get() = secure.getString("api_key", "").orEmpty()
        set(value) = secure.edit().putString("api_key", value.trim()).apply()

    var model: String
        get() = plain.getString("model", "deepseek-chat").orEmpty()
        set(value) = plain.edit().putString("model", value.trim()).apply()

    var style: String
        get() = plain.getString("style", "gradient-poster").orEmpty()
        set(value) = plain.edit().putString("style", value).apply()

    var size: String
        get() = plain.getString("size", "poster").orEmpty()
        set(value) = plain.edit().putString("size", value).apply()
}
