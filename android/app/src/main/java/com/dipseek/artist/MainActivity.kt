@file:OptIn(ExperimentalMaterial3Api::class)

package com.dipseek.artist

import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.AlertDialog
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

// --------------------------------------------------------------------------
// Мелкие модели: Compose любит стабильные типы, JSONObject для этого плох.
// --------------------------------------------------------------------------

private data class StyleOption(val id: String, val title: String)

private data class WorkItem(
    val name: String,
    val dir: String,
    val png: String?,
    val thumb: String?,
    val prompt: String,
)

private fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

private fun JSONArray?.strings(): List<String> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optString(it, null) }

/** Декодировать PNG, при необходимости уменьшив (для истории). */
private fun decode(path: String, maxSize: Int = 0): ImageBitmap? = try {
    if (maxSize <= 0) {
        BitmapFactory.decodeFile(path)?.asImageBitmap()
    } else {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, bounds)
        var sample = 1
        while (bounds.outWidth / sample > maxSize * 2 ||
            bounds.outHeight / sample > maxSize * 2
        ) {
            sample *= 2
        }
        BitmapFactory
            .decodeFile(path, BitmapFactory.Options().apply { inSampleSize = sample })
            ?.asImageBitmap()
    }
} catch (t: Throwable) {
    null
}

// --------------------------------------------------------------------------

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = Prefs(this)
        setContent {
            DipseekTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    AppScreen(prefs)
                }
            }
        }
    }
}

@Composable
private fun AppScreen(prefs: Prefs) {
    val scope = rememberCoroutineScope()

    var prompt by remember { mutableStateOf("") }
    var styles by remember { mutableStateOf<List<StyleOption>>(emptyList()) }
    var sizes by remember { mutableStateOf<List<String>>(emptyList()) }
    var styleId by remember { mutableStateOf(prefs.style) }
    var sizePreset by remember { mutableStateOf(prefs.size) }

    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var code by remember { mutableStateOf("") }
    var pngPath by remember { mutableStateOf<String?>(null) }
    var workDir by remember { mutableStateOf<String?>(null) }
    var works by remember { mutableStateOf<List<WorkItem>>(emptyList()) }
    var showSettings by remember { mutableStateOf(false) }
    var showCode by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf("") }

    fun loadWorks() {
        scope.launch {
            val data = withContext(Dispatchers.IO) { ArtistBridge.works() }
            works = data.optJSONArray("works").objects().map { o ->
                WorkItem(
                    name = o.optString("name"),
                    dir = o.optString("dir"),
                    png = o.optString("png", null),
                    thumb = o.optString("thumb", null),
                    prompt = o.optString("prompt", ""),
                )
            }
        }
    }

    LaunchedEffect(Unit) {
        val st = withContext(Dispatchers.IO) { ArtistBridge.styles() }
        styles = st.optJSONArray("styles").objects().map {
            StyleOption(it.optString("id"), it.optString("title"))
        }
        sizes = st.optJSONArray("sizes").strings()
        if (styles.isNotEmpty() && styles.none { it.id == styleId }) {
            styleId = styles.first().id
        }

        val doc = withContext(Dispatchers.IO) { ArtistBridge.doctor() }
        info = buildString {
            append("движок ")
            append(doc.optJSONObject("python_packages")?.toString() ?: "?")
            append(" · ")
            append(doc.optString("platform"))
        }

        val w = withContext(Dispatchers.IO) { ArtistBridge.works() }
        works = w.optJSONArray("works").objects().map { o ->
            WorkItem(
                name = o.optString("name"),
                dir = o.optString("dir"),
                png = o.optString("png", null),
                thumb = o.optString("thumb", null),
                prompt = o.optString("prompt", ""),
            )
        }

        if (prefs.apiKey.isBlank()) showSettings = true
    }

    fun draw() {
        if (prompt.isBlank()) {
            error = "Напиши, что нарисовать — например «закат над морем, минимализм»"
            return
        }
        if (prefs.apiKey.isBlank()) {
            showSettings = true
            return
        }
        busy = true
        error = null
        pngPath = null
        status = "DeepSeek пишет код картины…"
        scope.launch {
            val request = JSONObject().apply {
                put("prompt", prompt)
                put("style", styleId)
                put("size", sizePreset)
                put("api_key", prefs.apiKey)
                put("model", prefs.model)
                put("timeout", 240)
                put("repair", true)
            }
            val data = withContext(Dispatchers.IO) { ArtistBridge.draw(request) }
            busy = false
            code = data.optString("code", "")
            workDir = data.optString("work_dir", "").ifBlank { null }
            if (data.optBoolean("ok")) {
                pngPath = data.optString("png", null)
                val repair = if (data.optBoolean("self_repair")) " (с автопочинкой)" else ""
                status = "Готово за ${data.optDouble("seconds")} с$repair"
                error = null
                prefs.style = styleId
                prefs.size = sizePreset
                loadWorks()
            } else {
                status = ""
                error = data.optString("error") +
                    "\n\n" + data.optString("stderr", "") +
                    "\n" + data.optString("traceback", "")
            }
        }
    }

    fun rerender() {
        busy = true
        status = "Отрисовываю изменённый код…"
        scope.launch {
            val request = JSONObject().apply {
                put("code", code)
                put("work_dir", workDir ?: "")
                put("prompt", prompt)
                put("style", styleId)
                put("timeout", 240)
            }
            val data = withContext(Dispatchers.IO) { ArtistBridge.render(request) }
            busy = false
            showCode = false
            workDir = data.optString("work_dir", "").ifBlank { workDir }
            if (data.optBoolean("ok")) {
                pngPath = data.optString("png", null)
                status = "Готово за ${data.optDouble("seconds")} с"
                error = null
                loadWorks()
            } else {
                status = ""
                error = data.optString("error") + "\n\n" + data.optString("stderr", "")
            }
        }
    }

    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = "ДИПСИК ХУДОЖНИК",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { showSettings = true }) { Text("Ключ") }
        }

        OutlinedTextField(
            value = prompt,
            onValueChange = { prompt = it },
            label = { Text("Что нарисовать") },
            placeholder = { Text("закат над морем, минимализм, яркие цвета") },
            minLines = 2,
            modifier = Modifier.fillMaxWidth(),
        )

        if (styles.isNotEmpty()) {
            Text("Стиль", style = MaterialTheme.typography.labelLarge)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(styles.map { it.id }) { id ->
                    val title = styles.first { it.id == id }.title
                    FilterChip(
                        selected = id == styleId,
                        onClick = { styleId = id },
                        label = { Text(title, fontSize = 12.sp) },
                    )
                }
            }
        }

        if (sizes.isNotEmpty()) {
            Text("Размер", style = MaterialTheme.typography.labelLarge)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(sizes) { s ->
                    FilterChip(
                        selected = s == sizePreset,
                        onClick = { sizePreset = s },
                        label = { Text(s, fontSize = 12.sp) },
                    )
                }
            }
        }

        Button(
            onClick = { draw() },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (busy) "Рисую…" else "Нарисовать")
        }

        if (busy) {
            Column {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(4.dp))
                Text(status, style = MaterialTheme.typography.bodySmall)
            }
        } else if (status.isNotEmpty()) {
            Text(status, style = MaterialTheme.typography.bodySmall)
        }

        error?.let { message ->
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        "Не получилось",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.titleSmall,
                    )
                    Spacer(Modifier.height(6.dp))
                    SelectionContainer {
                        Text(
                            message.take(2000),
                            style = MaterialTheme.typography.bodySmall,
                            fontFamily = FontFamily.Monospace,
                            fontSize = 11.sp,
                        )
                    }
                    if (code.isNotBlank()) {
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(onClick = { showCode = true }) { Text("Показать код") }
                    }
                }
            }
        }

        pngPath?.let { path ->
            val bitmap = remember(path) { decode(path) }
            if (bitmap != null) {
                Image(
                    bitmap = bitmap,
                    contentDescription = "Готовая картина",
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp)),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = {
                        val msg = ImageSaver.saveToGallery(context, File(path))
                        status = msg
                    }) { Text("В галерею") }
                    OutlinedButton(onClick = {
                        val msg = ImageSaver.share(context, File(path))
                        if (msg.isNotEmpty()) status = msg
                    }) { Text("Поделиться") }
                    if (code.isNotBlank()) {
                        OutlinedButton(onClick = { showCode = true }) { Text("Код") }
                    }
                }
            }
        }

        if (works.isNotEmpty()) {
            HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            Text("Мои картины", style = MaterialTheme.typography.labelLarge)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(works.map { it.name }) { name ->
                    val item = works.first { it.name == name }
                    val thumb = item.thumb ?: item.png
                    val bmp = remember(thumb) { thumb?.let { decode(it, 160) } }
                    Column(
                        modifier = Modifier.width(96.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(
                            modifier = Modifier
                                .size(96.dp)
                                .clip(RoundedCornerShape(10.dp)),
                            contentAlignment = Alignment.Center,
                        ) {
                            if (bmp != null) {
                                Image(
                                    bitmap = bmp,
                                    contentDescription = item.prompt,
                                    modifier = Modifier.fillMaxSize(),
                                )
                            } else {
                                Text("?", color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Text(
                            item.prompt.ifBlank { item.name }.take(24),
                            style = MaterialTheme.typography.bodySmall,
                            fontSize = 10.sp,
                            maxLines = 2,
                        )
                    }
                }
            }
        }

        HorizontalDivider(color = MaterialTheme.colorScheme.outline)
        Text(
            text = info,
            style = MaterialTheme.typography.bodySmall,
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = "Ключ DeepSeek хранится только на этом устройстве. " +
                "Картину рисует Python-движок dipkit прямо в телефоне.",
            style = MaterialTheme.typography.bodySmall,
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    if (showSettings) {
        SettingsDialog(
            prefs = prefs,
            onDismiss = { showSettings = false },
            onSaved = { showSettings = false },
        )
    }

    if (showCode) {
        CodeDialog(
            code = code,
            onDismiss = { showCode = false },
            onRerender = { rerender() },
        )
    }
}

@Composable
private fun SettingsDialog(prefs: Prefs, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var key by remember { mutableStateOf(prefs.apiKey) }
    var model by remember { mutableStateOf(prefs.model) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Ключ DeepSeek") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "Ключ нужен, чтобы DeepSeek писал код картины. Он хранится " +
                        "в шифрованном виде на этом устройстве и никуда не отправляется, " +
                        "кроме api.deepseek.com.\n\n" +
                        "Получить: platform.deepseek.com → API keys.",
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedTextField(
                    value = key,
                    onValueChange = { key = it },
                    label = { Text("API-ключ") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = model,
                    onValueChange = { model = it },
                    label = { Text("Модель") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(onClick = {
                prefs.apiKey = key
                prefs.model = model.ifBlank { "deepseek-chat" }
                onSaved()
            }) { Text("Сохранить") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Позже") }
        },
    )
}

@Composable
private fun CodeDialog(code: String, onDismiss: () -> Unit, onRerender: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Код картины") },
        text = {
            Box(modifier = Modifier.heightIn(max = 420.dp)) {
                SelectionContainer {
                    Text(
                        text = code,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 10.sp,
                        modifier = Modifier.verticalScroll(rememberScrollState()),
                    )
                }
            }
        },
        confirmButton = {
            Button(onClick = onRerender) { Text("Отрисовать заново") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Закрыть") } },
    )
}
