package com.dipseek.artist

import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject

/**
 * Единственная точка входа в Python.
 *
 * Контракт намеренно примитивный: одна JSON-строка туда, одна обратно.
 * Так мост не зависит от преобразования типов Kotlin <-> Python, а весь
 * разбор ответа живёт в одном месте.
 *
 * Любая ошибка Python (включая неудачный импорт numpy/pillow) возвращается
 * как обычный ответ `{"ok": false, ...}` — приложение не должно падать.
 */
object ArtistBridge {

    private val module: PyObject by lazy { Python.getInstance().getModule("mobile") }

    private fun call(fn: String, payload: String? = null): JSONObject =
        try {
            val raw = if (payload == null) module.callAttr(fn) else module.callAttr(fn, payload)
            JSONObject(raw.toString())
        } catch (t: Throwable) {
            JSONObject()
                .put("ok", false)
                .put("error", "Сбой Python: ${t.message ?: t.javaClass.simpleName}")
                .put("traceback", t.stackTraceToString().take(1500))
        }

    fun version(): JSONObject = call("version")

    fun styles(): JSONObject = call("styles")

    fun doctor(): JSONObject = call("doctor")

    fun works(): JSONObject = call("works")

    fun draw(request: JSONObject): JSONObject = call("draw", request.toString())

    fun render(request: JSONObject): JSONObject = call("render", request.toString())

    fun workCode(dir: String): JSONObject =
        call("work_code", JSONObject().put("dir", dir).toString())

    fun deleteWork(dir: String): JSONObject =
        call("delete_work", JSONObject().put("dir", dir).toString())
}
