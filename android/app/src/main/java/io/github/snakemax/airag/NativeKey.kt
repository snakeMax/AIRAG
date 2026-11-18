package io.github.snakemax.airag

import java.security.MessageDigest
import java.security.SecureRandom

/**
 * The native bridges (speech, audio, sharing) are visible to every frame in the page, including the sandboxed
 * interactive explainer. Calls that do something need this key, which only AIRAG's own page receives (injected
 * for AIRAG's address only), so an explainer can't turn on the microphone, speak, change the volume or take
 * a shared file.
 */
object NativeKey {
    val value: String = ByteArray(24).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }

    fun ok(given: String?): Boolean =
        given != null && MessageDigest.isEqual(given.toByteArray(), value.toByteArray())
}
