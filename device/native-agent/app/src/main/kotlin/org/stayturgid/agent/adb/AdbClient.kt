package org.stayturgid.agent.adb

import android.os.Build
import android.util.Log
import org.stayturgid.agent.adb.AdbProtocol.ADB_AUTH_RSAPUBLICKEY
import org.stayturgid.agent.adb.AdbProtocol.ADB_AUTH_SIGNATURE
import org.stayturgid.agent.adb.AdbProtocol.ADB_AUTH_TOKEN
import org.stayturgid.agent.adb.AdbProtocol.A_AUTH
import org.stayturgid.agent.adb.AdbProtocol.A_CLSE
import org.stayturgid.agent.adb.AdbProtocol.A_CNXN
import org.stayturgid.agent.adb.AdbProtocol.A_MAXDATA
import org.stayturgid.agent.adb.AdbProtocol.A_OKAY
import org.stayturgid.agent.adb.AdbProtocol.A_OPEN
import org.stayturgid.agent.adb.AdbProtocol.A_STLS
import org.stayturgid.agent.adb.AdbProtocol.A_STLS_VERSION
import org.stayturgid.agent.adb.AdbProtocol.A_VERSION
import org.stayturgid.agent.adb.AdbProtocol.A_WRTE
import java.io.Closeable
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.net.ssl.SSLSocket

/**
 * Minimal ADB client the agent uses to reach a remote device's `adbd` and run a
 * shell command (the Shizuku starter — see [org.stayturgid.agent.PeerStarter]).
 *
 * Ported from the Shizuku fork's `moe.shizuku.manager.adb.AdbClient`. Adaptations
 * vs. upstream: package rename, `BuildUtils.atLeast29` → inline SDK check, the
 * debug `logd` import dropped, and a configurable [readTimeoutMs] so the one-time
 * "Always allow" authorization on a new target doesn't block a background thread
 * forever (upstream relied on the interactive UI to bound the wait).
 */
private const val TAG = "StayTurgidAdbClient"

class AdbClient(
    private val host: String,
    private val port: Int,
    private val key: AdbKey,
    private val connectTimeoutMs: Int = 5000,
    private val readTimeoutMs: Int = 60_000,
) : Closeable {
    private lateinit var socket: Socket
    private lateinit var plainInputStream: DataInputStream
    private lateinit var plainOutputStream: DataOutputStream

    private var useTls = false

    private lateinit var tlsSocket: SSLSocket
    private lateinit var tlsInputStream: DataInputStream
    private lateinit var tlsOutputStream: DataOutputStream

    private val inputStream get() = if (useTls) tlsInputStream else plainInputStream
    private val outputStream get() = if (useTls) tlsOutputStream else plainOutputStream

    fun connect() {
        // ADB transport is a plaintext framed protocol authenticated by RSA
        // (A_AUTH) and optionally upgraded to TLS (A_STLS) — the initial socket
        // is necessarily unencrypted. This fleet only ever dials adbd over
        // Tailscale (WireGuard), so the link is encrypted at the network layer.
        val socket = Socket() // nosemgrep: kotlin.lang.security.unencrypted-socket.unencrypted-socket
        val address = InetSocketAddress(host, port)
        socket.connect(address, connectTimeoutMs)

        socket.tcpNoDelay = true
        // Bound blocking reads. The A_AUTH RSAPUBLICKEY handshake with an
        // unrecognized key waits on a human "Always allow" tap on the target;
        // readTimeoutMs keeps that from wedging the peer-start thread.
        socket.soTimeout = readTimeoutMs
        this.socket = socket
        plainInputStream = DataInputStream(socket.getInputStream())
        plainOutputStream = DataOutputStream(socket.getOutputStream())

        write(A_CNXN, A_VERSION, A_MAXDATA, "host::")

        // Once the target has issued an auth challenge it is reachable and
        // simply waiting on the operator's "Always allow" — surface a read
        // timeout past this point as pending-approval, not offline.
        var challenged = false
        val message =
            try {
                connectHandshake { challenged = true }
            } catch (e: SocketTimeoutException) {
                if (challenged) {
                    throw AdbAuthPendingException("target reachable; awaiting one-time ADB approval")
                }
                throw e
            }

        if (message.command != A_CNXN) error("not A_CNXN")
    }

    private inline fun connectHandshake(onChallenged: () -> Unit): AdbMessage {
        var message = read()
        if (message.command == A_STLS) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                error("Connect to adb with TLS is not supported before Android 9")
            }
            write(A_STLS, A_STLS_VERSION, 0)

            val sslContext = key.sslContext
            tlsSocket = sslContext.socketFactory.createSocket(socket, host, port, true) as SSLSocket
            tlsSocket.startHandshake()
            Log.d(TAG, "Handshake succeeded.")

            tlsInputStream = DataInputStream(tlsSocket.inputStream)
            tlsOutputStream = DataOutputStream(tlsSocket.outputStream)
            useTls = true

            message = read()
        } else if (message.command == A_AUTH) {
            onChallenged()
            if (message.command != A_AUTH && message.arg0 != ADB_AUTH_TOKEN) error("not A_AUTH ADB_AUTH_TOKEN")
            write(A_AUTH, ADB_AUTH_SIGNATURE, 0, key.sign(message.data))

            message = read()
            if (message.command != A_CNXN) {
                write(A_AUTH, ADB_AUTH_RSAPUBLICKEY, 0, key.adbPublicKey)
                message = read()
            }
        }
        return message
    }

    fun command(
        cmd: String,
        listener: ((ByteArray) -> Unit)? = null,
    ) {
        val localId = 1
        write(A_OPEN, localId, 0, cmd)

        var message = read()
        when (message.command) {
            A_OKAY -> {
                while (true) {
                    message = read()
                    val remoteId = message.arg0
                    if (message.command == A_WRTE) {
                        if (message.data_length > 0) {
                            listener?.invoke(message.data!!)
                        }
                        write(A_OKAY, localId, remoteId)
                    } else if (message.command == A_CLSE) {
                        write(A_CLSE, localId, remoteId)
                        break
                    } else {
                        error("not A_WRTE or A_CLSE")
                    }
                }
            }
            A_CLSE -> {
                val remoteId = message.arg0
                write(A_CLSE, localId, remoteId)
            }
            else -> {
                error("not A_OKAY or A_CLSE")
            }
        }
    }

    private fun write(
        command: Int,
        arg0: Int,
        arg1: Int,
        data: ByteArray? = null,
    ) = write(AdbMessage(command, arg0, arg1, data))

    private fun write(
        command: Int,
        arg0: Int,
        arg1: Int,
        data: String,
    ) = write(AdbMessage(command, arg0, arg1, data))

    private fun write(message: AdbMessage) {
        outputStream.write(message.toByteArray())
        outputStream.flush()
        Log.d(TAG, "write ${message.toStringShort()}")
    }

    private fun read(): AdbMessage {
        val buffer = ByteBuffer.allocate(AdbMessage.HEADER_LENGTH).order(ByteOrder.LITTLE_ENDIAN)

        inputStream.readFully(buffer.array(), 0, 24)

        val command = buffer.int
        val arg0 = buffer.int
        val arg1 = buffer.int
        val dataLength = buffer.int
        val checksum = buffer.int
        val magic = buffer.int
        val data: ByteArray?
        if (dataLength >= 0) {
            data = ByteArray(dataLength)
            inputStream.readFully(data, 0, dataLength)
        } else {
            data = null
        }
        val message = AdbMessage(command, arg0, arg1, dataLength, checksum, magic, data)
        message.validateOrThrow()
        Log.d(TAG, "read ${message.toStringShort()}")
        return message
    }

    override fun close() {
        try {
            plainInputStream.close()
        } catch (_: Throwable) {
        }
        try {
            plainOutputStream.close()
        } catch (_: Throwable) {
        }
        try {
            socket.close()
        } catch (_: Exception) {
        }

        if (useTls) {
            try {
                tlsInputStream.close()
            } catch (_: Throwable) {
            }
            try {
                tlsOutputStream.close()
            } catch (_: Throwable) {
            }
            try {
                tlsSocket.close()
            } catch (_: Exception) {
            }
        }
    }
}
