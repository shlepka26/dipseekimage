package com.dipseek.artist

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File

/** Сохранение картины в галерею и отправка через «Поделиться». */
object ImageSaver {

    /**
     * Кладёт PNG в галерею. На Android 10+ это обычная запись через MediaStore
     * (разрешения не нужны). На более старых версиях прямая запись в общую
     * галерею требует разрешения, поэтому файл остаётся в папке приложения,
     * а пользователю предлагается «Поделиться» — так приложение не просит
     * лишних прав.
     */
    fun saveToGallery(context: Context, file: File): String = try {
        val name = "dipseek-${System.currentTimeMillis()}.png"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(
                    MediaStore.Images.Media.RELATIVE_PATH,
                    Environment.DIRECTORY_PICTURES + "/DipseekArtist",
                )
                put(MediaStore.Images.Media.IS_PENDING, 1)
            }
            val resolver = context.contentResolver
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: return "Не удалось создать запись в галерее"
            resolver.openOutputStream(uri)?.use { out ->
                file.inputStream().use { input -> input.copyTo(out) }
            } ?: return "Не удалось записать файл"
            values.clear()
            values.put(MediaStore.Images.Media.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            "Сохранено: Pictures/DipseekArtist/$name"
        } else {
            val dir = context.getExternalFilesDir(Environment.DIRECTORY_PICTURES)
                ?: context.filesDir
            val dst = File(dir, name)
            file.copyTo(dst, overwrite = true)
            "Сохранено: ${dst.absolutePath}\nНа Android до 10 отправь через «Поделиться»"
        }
    } catch (t: Throwable) {
        "Ошибка сохранения: ${t.message}"
    }

    /** Открыть системное «Поделиться» для PNG. Пустая строка = всё хорошо. */
    fun share(context: Context, file: File): String = try {
        val uri: Uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file,
        )
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "image/png"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        context.startActivity(Intent.createChooser(intent, "Поделиться картиной"))
        ""
    } catch (t: Throwable) {
        "Не удалось поделиться: ${t.message}"
    }
}
