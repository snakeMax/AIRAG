package io.github.snakemax.airag

import android.net.Uri

/**
 * Same rule as airag/netguard.py for the phone's WebViews: pages AIRAG reads may not lead to this phone
 * or the local network, and only web links (and mail links the user taps) may leave AIRAG.
 * Names are checked as written (literal addresses and local-only names); the Python side also resolves
 * names before reading a page.
 */
object NetGuard {
    private val LOCAL_SUFFIXES = listOf(".local", ".localhost", ".lan", ".home", ".internal", ".intranet", ".corp", ".home.arpa")

    fun isWeb(uri: Uri): Boolean = uri.scheme == "http" || uri.scheme == "https"

    /** Schemes AIRAG's own page may hand to another app when the reader taps a link. */
    fun externalOk(uri: Uri): Boolean = isWeb(uri) || uri.scheme == "mailto"

    fun isLocal(uri: Uri): Boolean {
        val host = (uri.host ?: return true).trim('.', '[', ']').lowercase()
        if (host.isEmpty() || host == "localhost" || LOCAL_SUFFIXES.any { host.endsWith(it) }) return true
        if (!host.contains('.') && !host.contains(':')) return true          // "router", "nas"
        if (host.contains(':')) {                                             // IPv6
            return host == "::1" || host == "::" || host.startsWith("fc") || host.startsWith("fd") ||
                host.startsWith("fe80") || host.startsWith("::ffff:")
        }
        val parts = host.split('.')
        if (parts.size == 4 && parts.all { p -> p.isNotEmpty() && p.all { it.isDigit() } }) {
            val n = parts.map { it.toIntOrNull() ?: return true }
            val (a, b) = n[0] to n[1]
            return a == 0 || a == 10 || a == 127 || (a == 169 && b == 254) || (a == 172 && b in 16..31) ||
                (a == 192 && b == 168) || (a == 100 && b in 64..127) || a >= 224
        }
        // other numeric spellings (2130706433, 0x7f.1) are refused
        return parts.all { p -> p.all { it.isDigit() || it == 'x' || it in 'a'..'f' } } && parts.any { p -> p.any { it.isDigit() } } && parts.last().all { it.isDigit() || it == 'x' }
    }
}
