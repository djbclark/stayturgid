package org.stayturgid.agent

import android.content.Context
import android.hardware.input.InputManager
import android.os.SystemClock
import android.util.Log
import android.view.InputDevice
import android.view.InputEvent
import android.view.KeyCharacterMap
import android.view.KeyEvent
import androidx.annotation.Keep
import java.lang.reflect.Method

/**
 * Runs as UID 2000 (shell) under Shizuku. No non-SDK restrictions.
 *
 * Phase 1 payload: [pingAwake] injects a silent key event via InputManager
 * reflection — never Runtime.exec / Shizuku.newProcess.
 */
class ShizukuUserService : IStayTurgidService.Stub {
    private var appContext: Context? = null

    constructor() {
        Log.i(TAG, "constructor")
    }

    /**
     * Available from Shizuku API v13. Prefer this — Context.getSystemService works
     * for InputManager on modern Android where getInstance() was removed.
     */
    @Keep
    constructor(context: Context) {
        appContext = context.applicationContext ?: context
        Log.i(TAG, "constructor with Context: $context")
    }

    override fun destroy() {
        Log.i(TAG, "destroy")
        System.exit(0)
    }

    override fun pingAwake() {
        try {
            injectSilentKey()
            Log.i(TAG, "pingAwake ok")
        } catch (t: Throwable) {
            Log.e(TAG, "pingAwake failed", t)
        }
    }

    override fun runComonitor(): String {
        return try {
            ComonitorProbes.runAndLog()
        } catch (t: Throwable) {
            Log.e(TAG, "runComonitor failed", t)
            "[agent] STATUS error=${t.message}"
        }
    }

    override fun repairCatastrophic(): String {
        return try {
            val r = CatastrophicRepair.repair()
            Log.i(TAG, "repairCatastrophic ok=${r.ok} detail=${r.detail}")
            // Re-probe after repair so agent.log has a fresh STATUS.
            runComonitor()
            "ok=${r.ok} detail=${r.detail}"
        } catch (t: Throwable) {
            Log.e(TAG, "repairCatastrophic failed", t)
            "ok=false detail=${t.message}"
        }
    }

    override fun repairTailscale(): String {
        return try {
            val r = CatastrophicRepair.repairTailscale()
            Log.i(TAG, "repairTailscale ok=${r.ok} detail=${r.detail}")
            runComonitor()
            "ok=${r.ok} detail=${r.detail}"
        } catch (t: Throwable) {
            Log.e(TAG, "repairTailscale failed", t)
            "ok=false detail=${t.message}"
        }
    }

    private fun injectSilentKey() {
        val inputManager = resolveInputManager()
        val inject = resolveInjectMethod(inputManager.javaClass)
        val now = SystemClock.uptimeMillis()
        // KEYCODE_UNKNOWN is silent; IME-sensitive paths may ignore pure keys —
        // MotionEvent path can be added later after device soak.
        val down =
            KeyEvent(
                now,
                now,
                KeyEvent.ACTION_DOWN,
                KeyEvent.KEYCODE_UNKNOWN,
                0,
                0,
                KeyCharacterMap.VIRTUAL_KEYBOARD,
                0,
                KeyEvent.FLAG_FROM_SYSTEM,
                InputDevice.SOURCE_KEYBOARD,
            )
        val up =
            KeyEvent(
                now,
                now,
                KeyEvent.ACTION_UP,
                KeyEvent.KEYCODE_UNKNOWN,
                0,
                0,
                KeyCharacterMap.VIRTUAL_KEYBOARD,
                0,
                KeyEvent.FLAG_FROM_SYSTEM,
                InputDevice.SOURCE_KEYBOARD,
            )
        // mode 0 = INJECT_INPUT_EVENT_MODE_ASYNC
        inject.invoke(inputManager, down, 0)
        inject.invoke(inputManager, up, 0)
    }

    private fun resolveInputManager(): Any {
        // 1) Context path (Shizuku API v13+ Context constructor).
        val ctx = appContext
        if (ctx != null) {
            val fromCtx = ctx.getSystemService(InputManager::class.java)
            if (fromCtx != null) {
                Log.i(TAG, "InputManager via Context")
                return fromCtx
            }
        }

        val clazz = Class.forName("android.hardware.input.InputManager")

        // 2) getInstance() on older platform builds.
        try {
            val getInstance: Method = clazz.getDeclaredMethod("getInstance")
            getInstance.isAccessible = true
            val im = getInstance.invoke(null)
            if (im != null) {
                Log.i(TAG, "InputManager via getInstance()")
                return im
            }
        } catch (t: Throwable) {
            Log.w(TAG, "InputManager.getInstance unavailable: ${t.message}")
        }

        // 3) IInputManager binder (scrcpy-style).
        try {
            val sm = Class.forName("android.os.ServiceManager")
            val getService = sm.getMethod("getService", String::class.java)
            val binder = getService.invoke(null, "input")
                ?: error("ServiceManager.getService(input) null")
            val stub = Class.forName("android.hardware.input.IInputManager\$Stub")
            val asInterface = stub.getMethod("asInterface", Class.forName("android.os.IBinder"))
            val iim = asInterface.invoke(null, binder)
                ?: error("IInputManager.Stub.asInterface null")
            Log.i(TAG, "InputManager via IInputManager binder")
            return iim
        } catch (t: Throwable) {
            throw IllegalStateException("Could not resolve InputManager / IInputManager", t)
        }
    }

    private fun resolveInjectMethod(clazz: Class<*>): Method {
        // Concrete InputManager or IInputManager both expose injectInputEvent(InputEvent, int).
        val candidates =
            sequenceOf(clazz)
                .flatMap { c -> generateSequence(c) { it.superclass } }
                .flatMap { c -> c.methods.asSequence() + c.declaredMethods.asSequence() }
                .filter { it.name == "injectInputEvent" }
                .toList()

        val match =
            candidates.firstOrNull { m ->
                val p = m.parameterTypes
                p.size == 2 &&
                    InputEvent::class.java.isAssignableFrom(p[0]) &&
                    (p[1] == Int::class.javaPrimitiveType || p[1] == Integer::class.java)
            }
                ?: candidates.firstOrNull { it.parameterTypes.size == 2 }
                ?: error(
                    "injectInputEvent not found on ${clazz.name}; methods=" +
                        candidates.map { it.toGenericString() },
                )
        match.isAccessible = true
        return match
    }

    companion object {
        private const val TAG = "StayTurgidUS"
    }
}
