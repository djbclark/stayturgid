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
