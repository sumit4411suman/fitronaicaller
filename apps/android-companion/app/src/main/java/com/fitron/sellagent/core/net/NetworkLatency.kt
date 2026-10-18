package com.fitron.sellagent.core.net

import com.fitron.sellagent.core.security.Pairing

/** Round-trip time of GET /api/v1/health/ping over the pinned TLS client; this is the PC link latency, not call audio latency. */
object NetworkLatency {
    data class Result(val ok: Boolean, val medianMs: Double, val samples: Int, val detail: String)

    suspend fun measure(pairing: Pairing, rounds: Int = 3): Result {
        val client = runCatching { PairingClient(pairing.host, pairing.port, pairing.tlsFingerprint) }
            .getOrElse { return Result(false, 0.0, 0, "client: ${it.message}") }
        val times = mutableListOf<Double>()
        repeat(rounds) {
            val t0 = System.nanoTime()
            val r = runCatching { client.ping() }
            if (r.isFailure) return Result(false, 0.0, times.size, "${r.exceptionOrNull()?.javaClass?.simpleName}: ${r.exceptionOrNull()?.message ?: ""}")
            times.add((System.nanoTime() - t0) / 1e6)
        }
        val sorted = times.sorted()
        val median = sorted[sorted.size / 2]
        return Result(true, median, times.size, "HTTPS ping to ${pairing.host}:${pairing.port}, pinned certificate")
    }
}
