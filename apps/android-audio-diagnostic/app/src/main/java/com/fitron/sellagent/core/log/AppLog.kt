package com.fitron.sellagent.core.log

import android.content.Context
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

enum class LogLevel { DEBUG, INFO, WARN, ERROR }

data class LogEntry(val time: String, val level: LogLevel, val tag: String, val message: String) {
    fun line(): String = "$time ${level.name.padEnd(5)} [$tag] $message"
}

/**
 * App-wide diagnostic log: in-memory ring buffer of the last 1000 entries plus a rotating file
 * (files/logs/app.log, rotated to app.log.1 at 256 KB). Every message passes through [sanitize] first, so the
 * log never contains tokens, certificate fingerprints or full phone numbers (numbers keep their last 4 digits).
 */
object AppLog {
    private const val CAPACITY = 1000
    private const val MAX_FILE_BYTES = 256 * 1024L
    private val lock = Any()
    private val buffer = ArrayDeque<LogEntry>(CAPACITY)
    private val writer = Executors.newSingleThreadExecutor { r -> Thread(r, "sellagent-applog").apply { isDaemon = true } }
    private val stamp = DateTimeFormatter.ofPattern("MM-dd HH:mm:ss")
    @Volatile private var dir: File? = null

    private val _entries = MutableStateFlow<List<LogEntry>>(emptyList())
    val entries: StateFlow<List<LogEntry>> = _entries

    fun init(context: Context) {
        dir = File(context.filesDir, "logs").apply { mkdirs() }
    }

    fun d(tag: String, msg: String) = add(LogLevel.DEBUG, tag, msg)
    fun i(tag: String, msg: String) = add(LogLevel.INFO, tag, msg)
    fun w(tag: String, msg: String) = add(LogLevel.WARN, tag, msg)
    fun e(tag: String, msg: String) = add(LogLevel.ERROR, tag, msg)

    fun add(level: LogLevel, tag: String, msg: String) {
        val entry = LogEntry(LocalDateTime.now().format(stamp), level, tag.take(24), sanitize(msg).take(600))
        synchronized(lock) {
            if (buffer.size >= CAPACITY) buffer.removeFirst()
            buffer.addLast(entry)
            _entries.value = buffer.toList()
        }
        val d = dir ?: return
        writer.execute {
            runCatching {
                val f = File(d, "app.log")
                if (f.length() > MAX_FILE_BYTES) {
                    val old = File(d, "app.log.1")
                    old.delete()
                    f.renameTo(old)
                }
                File(d, "app.log").appendText(entry.line() + "\n")
            }
        }
    }

    fun clear() {
        synchronized(lock) {
            buffer.clear()
            _entries.value = emptyList()
        }
        val d = dir ?: return
        writer.execute { runCatching { File(d, "app.log").delete(); File(d, "app.log.1").delete() } }
    }

    fun asText(filter: Set<LogLevel> = LogLevel.entries.toSet()): String =
        _entries.value.filter { it.level in filter }.joinToString("\n") { it.line() }

    private val bearer = Regex("(?i)bearer\\s+\\S+")
    private val tokenKv = Regex("(?i)(token|authorization|device_token|authorization_token)([\"']?\\s*[:=]\\s*[\"']?)[^\\s\"',}]+")
    private val fingerprint = Regex("\\b(?:[0-9A-Fa-f]{2}:){7,}[0-9A-Fa-f]{2}\\b")
    private val longHex = Regex("\\b[0-9A-Fa-f]{32,}\\b")
    private val longSecret = Regex("\\b[A-Za-z0-9_\\-]{40,}\\b")
    private val phone = Regex("\\+\\d[\\d\\s\\-]{5,}\\d|\\b\\d{10,}\\b")

    /** Removes secrets and masks phone numbers to their last 4 digits. Public for unit tests. */
    fun sanitize(input: String): String {
        var s = bearer.replace(input, "Bearer [redacted]")
        s = tokenKv.replace(s) { m -> m.groupValues[1] + m.groupValues[2] + "[redacted]" }
        s = fingerprint.replace(s, "[fingerprint]")
        s = longHex.replace(s, "[redacted]")
        s = longSecret.replace(s, "[redacted]")
        s = phone.replace(s) { m ->
            val digits = m.value.filter { it.isDigit() }
            if (digits.length < 7) m.value else "…" + digits.takeLast(4)
        }
        return s
    }
}
