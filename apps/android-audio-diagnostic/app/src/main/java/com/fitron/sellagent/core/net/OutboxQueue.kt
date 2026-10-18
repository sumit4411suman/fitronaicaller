package com.fitron.sellagent.core.net

import com.fitron.sellagent.protocol.Envelope
import java.io.File

/**
 * File-backed queue of envelopes that have not yet been acknowledged by the backend. One JSON envelope per line.
 * Survives process death; replayed in order after every (re)connect. Access is synchronized; the file is small.
 */
class OutboxQueue(private val file: File) {
    private val lock = Any()
    private val items = LinkedHashMap<String, Envelope>()

    init {
        synchronized(lock) {
            if (file.exists()) {
                file.forEachLine { line ->
                    if (line.isNotBlank()) {
                        runCatching { Envelope.parse(line) }.getOrNull()?.let { items[it.messageId] = it }
                    }
                }
            }
        }
    }

    fun add(env: Envelope) = synchronized(lock) {
        items[env.messageId] = env
        persist()
    }

    fun remove(messageId: String): Boolean = synchronized(lock) {
        val removed = items.remove(messageId) != null
        if (removed) persist()
        removed
    }

    fun snapshot(): List<Envelope> = synchronized(lock) { items.values.toList() }

    fun size(): Int = synchronized(lock) { items.size }

    fun clear() = synchronized(lock) {
        items.clear()
        persist()
    }

    private fun persist() {
        runCatching {
            file.parentFile?.mkdirs()
            val tmp = File(file.parentFile, file.name + ".tmp")
            tmp.writeText(items.values.joinToString("\n") { it.toJson() })
            if (!tmp.renameTo(file)) {
                file.writeText(tmp.readText())
                tmp.delete()
            }
        }
    }
}
