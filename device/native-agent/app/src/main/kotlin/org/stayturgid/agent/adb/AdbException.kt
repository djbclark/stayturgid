package org.stayturgid.agent.adb

/**
 * Ported from the Shizuku fork's `moe.shizuku.manager.adb.AdbException`
 * (package changed; pairing-only subclasses dropped — the agent never pairs,
 * it uses classic `adb tcpip 5555` + RSA A_AUTH).
 */
@Suppress("NOTHING_TO_INLINE")
inline fun adbError(message: Any): Nothing = throw AdbException(message.toString())

open class AdbException : Exception {
    constructor(message: String, cause: Throwable?) : super(message, cause)
    constructor(message: String) : super(message)
    constructor(cause: Throwable) : super(cause)
    constructor()
}

class AdbKeyException(cause: Throwable) : AdbException(cause)

/**
 * Thrown when the target's `adbd` was reached and issued an auth challenge, but
 * no approval arrived before the read timeout — i.e. the operator hasn't yet
 * ticked "Always allow" on the target for this key. Distinct from a plain
 * connection failure so callers can nag for the one-time authorization rather
 * than treat the target as offline.
 */
class AdbAuthPendingException(message: String) : AdbException(message)
