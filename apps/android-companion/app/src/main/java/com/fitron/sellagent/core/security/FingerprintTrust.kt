package com.fitron.sellagent.core.security

import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.Locale
import java.util.concurrent.TimeUnit
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSession
import javax.net.ssl.X509TrustManager
import okhttp3.OkHttpClient

/**
 * Certificate pinning for the self-signed LAN listener of the local backend.
 *
 * The Windows pairing screen shows the SHA-256 fingerprint of the server certificate (DER encoding, "AA:BB:..").
 * The user types it into the app during pairing. From then on every TLS handshake to the backend is accepted ONLY if
 * the leaf certificate presented by the server hashes to exactly that fingerprint. Nothing else is trusted:
 * no CA store, no "accept all" fallback, and the trust manager is installed on this one OkHttpClient only.
 */
object FingerprintTrust {

    /** Normalises user input ("aa:bb", "AABB", with spaces) to "AA:BB:...". Returns null if it is not 32 bytes. */
    fun normalize(input: String): String? {
        val hex = input.uppercase(Locale.ROOT).filter { it in "0123456789ABCDEF" }
        if (hex.length != 64) return null
        return hex.chunked(2).joinToString(":")
    }

    fun sha256Fingerprint(cert: X509Certificate): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(cert.encoded)
        return digest.joinToString(":") { String.format(Locale.ROOT, "%02X", it) }
    }

    /** Accepts exactly one server certificate, identified by its SHA-256 fingerprint. */
    class PinnedTrustManager(pinnedFingerprint: String) : X509TrustManager {
        private val pin: String = normalize(pinnedFingerprint)
            ?: throw IllegalArgumentException("fingerprint must be 32 bytes of hex")

        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {
            throw CertificateException("client certificates are not used")
        }

        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            if (chain.isEmpty()) throw CertificateException("empty certificate chain")
            val leaf = chain[0]
            leaf.checkValidity()
            val actual = sha256Fingerprint(leaf)
            if (actual != pin) {
                throw CertificateException("server certificate fingerprint $actual does not match the pinned fingerprint")
            }
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }

    /**
     * Hostname verification for a pinned self-signed certificate. The standard RFC 2818 check runs first; when it fails
     * (the backend certificate only lists localhost/127.0.0.1 in its SANs, while the phone connects by LAN IP) the
     * connection is still accepted if and only if the presented certificate is the pinned one. This verifier is
     * installed on the pinned client only, never globally.
     */
    class PinnedHostnameVerifier(pinnedFingerprint: String) : HostnameVerifier {
        private val pin: String = normalize(pinnedFingerprint)
            ?: throw IllegalArgumentException("fingerprint must be 32 bytes of hex")

        override fun verify(hostname: String, session: SSLSession): Boolean {
            val standard = HttpsURLConnection.getDefaultHostnameVerifier()
            if (standard.verify(hostname, session)) return true
            val peer = runCatching { session.peerCertificates }.getOrNull() ?: return false
            val leaf = peer.firstOrNull() as? X509Certificate ?: return false
            return sha256Fingerprint(leaf) == pin
        }
    }

    /** Builds an OkHttpClient that trusts only the pinned backend certificate. */
    fun pinnedClient(pinnedFingerprint: String): OkHttpClient {
        val tm = PinnedTrustManager(pinnedFingerprint)
        val ctx = SSLContext.getInstance("TLS")
        ctx.init(null, arrayOf<X509TrustManager>(tm), null)
        return OkHttpClient.Builder()
            .sslSocketFactory(ctx.socketFactory, tm)
            .hostnameVerifier(PinnedHostnameVerifier(pinnedFingerprint))
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .pingInterval(25, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }
}
