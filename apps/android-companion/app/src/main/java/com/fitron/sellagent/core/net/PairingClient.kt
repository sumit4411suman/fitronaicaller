package com.fitron.sellagent.core.net

import com.fitron.sellagent.core.security.FingerprintTrust
import com.fitron.sellagent.protocol.PairingRequest
import com.fitron.sellagent.protocol.PairingResponse
import com.fitron.sellagent.protocol.PairingResult
import com.fitron.sellagent.protocol.ProtocolJson
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** HTTP side of pairing (POST pair, poll result, GET me). All calls run on Dispatchers.IO. */
class PairingClient(host: String, port: Int, fingerprint: String) {
    private val client: OkHttpClient = FingerprintTrust.pinnedClient(fingerprint)
    private val base: HttpUrl = "https://$host:$port/".toHttpUrlOrNull()
        ?: throw IllegalArgumentException("invalid host or port")

    class HttpFailure(val code: Int, val body: String) : IOException("HTTP $code: ${body.take(300)}")

    suspend fun ping(): String = withContext(Dispatchers.IO) {
        execute(Request.Builder().url(base.resolve("api/v1/health/ping")!!).get().build())
    }

    suspend fun pair(req: PairingRequest): PairingResponse = withContext(Dispatchers.IO) {
        val body = ProtocolJson.encodeToString(req).toRequestBody(JSON)
        val raw = execute(Request.Builder().url(base.resolve("api/v1/devices/pair")!!).post(body).build())
        ProtocolJson.decodeFromString(PairingResponse.serializer(), raw)
    }

    suspend fun pollResult(devicePublicId: String): PairingResult = withContext(Dispatchers.IO) {
        val url = base.resolve("api/v1/devices/pair/result")!!.newBuilder()
            .addQueryParameter("device_public_id", devicePublicId).build()
        val raw = execute(Request.Builder().url(url).get().build())
        ProtocolJson.decodeFromString(PairingResult.serializer(), raw)
    }

    /** GET /api/v1/devices/me with the bearer token; returns the raw JSON (device record) or throws. */
    suspend fun me(deviceToken: String): String = withContext(Dispatchers.IO) {
        execute(
            Request.Builder().url(base.resolve("api/v1/devices/me")!!)
                .header("Authorization", "Bearer $deviceToken").get().build(),
        )
    }

    private fun execute(request: Request): String {
        client.newCall(request).execute().use { resp ->
            val text = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw HttpFailure(resp.code, text)
            return text
        }
    }

    private companion object {
        val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
