// Ambient globals provided by the AutoJs6 Rhino runtime.
//
// This is deliberately NOT a general-purpose AutoJs6 API surface — it covers
// only what device/autojs6/**/*.ts and docs/research/autojs6-hd8-project/*.ts
// actually call, typed from observed usage. AutoJs6 has no first-party .d.ts
// package with real content (@sm003/autojs6-dts on npm ships empty stub
// files; the real declarations are a separate multi-MB GitHub archive
// covering the full Android SDK surface, far beyond what this fleet-watchdog
// codebase touches).
//
// Globals that may not exist on every AutoJs6 build/version are typed
// `| undefined` rather than assumed-present, matching the `typeof x !==
// "undefined"` guards already used at every call site — the type checker now
// enforces the same guard the original JS did defensively.

declare function sleep(ms: number): void;
declare function toast(message: string): void;
declare function setInterval(handler: () => void, timeoutMs: number): number;
declare function setTimeout(handler: () => void, timeoutMs: number): number;

interface Console {
  log(...args: unknown[]): void;
  warn(...args: unknown[]): void;
  error(...args: unknown[]): void;
}
declare const console: Console;

interface FilesApi {
  exists(path: string): boolean;
  read(path: string): string;
  write(path: string, content: string): void;
  append(path: string, content: string): void;
  ensureDir(path: string): void;
}
declare const files: FilesApi;

/** Result of a shell() invocation: process exit code + captured stdout/stderr. */
interface ShellResult {
  code: number;
  result: string;
  /** stderr output — e.g. "Permission denied" when root was needed but not granted. */
  error?: string;
}
declare function shell(command: string, sync: boolean): ShellResult;

interface AppStartActivityOptions {
  packageName: string;
  className: string;
  flags?: string[];
}
interface AppStartServiceOptions {
  action: string;
  packageName: string;
  className: string;
  extras?: Record<string, string>;
}
interface AppApi {
  startActivity(options: AppStartActivityOptions): void;
  startService(options: AppStartServiceOptions): void;
}
declare const app: AppApi;

declare const device: {
  sdkInt: number;
};

declare namespace android.content {
  /**
   * Raw Java interop escape hatch — used instead of app.startService() when a
   * receiving component reads a boolean extra via Intent#getBooleanExtra().
   * app.startService()'s `extras` option can only send string-typed extras
   * (see AppStartServiceOptions above); a String-typed extra read via
   * getBooleanExtra() silently resolves to that method's default value
   * instead of throwing, so the intended value never arrives.
   */
  class Intent {
    constructor(action?: string);
    setClassName(packageName: string, className: string): Intent;
    putExtra(name: string, value: string): Intent;
    putExtra(name: string, value: boolean): Intent;
  }
}

/** A running AutoJs6 script engine (as returned by engines.all() / myEngine()). */
interface Engine {
  id: unknown;
  getSource(): string | null;
  forceStop(): void;
}
interface EngineApi {
  all(): Engine[];
  myEngine(): Engine | null;
  execScriptFile(path: string, config: org.autojs.autojs.execution.ExecutionConfig): void;
}
declare const engines: EngineApi;
declare const runtime: {
  engines: EngineApi;
};

declare const context: {
  getSystemService(serviceName: string): unknown;
  NOTIFICATION_SERVICE: string;
  startService(intent: android.content.Intent): unknown;
};

interface ThreadHandle {
  join(timeoutMs: number): void;
}
declare const threads: {
  start(fn: () => void): ThreadHandle;
};

declare const timers:
  | {
      keepAlive?: () => void;
    }
  | undefined;

/** AutoJs6's accessibility-service handle; present only under the `"auto";` mode directive. */
declare const auto:
  | {
      service: unknown;
      waitFor(): void;
    }
  | undefined;

/**
 * Shizuku privileged-shell bridge. Callable directly (runs a command) and
 * carries optional status properties/methods depending on AutoJs6 version —
 * every call site checks for both function-ness and member presence before use.
 */
interface ShizukuApi {
  (command: string): ShellResult;
  isOperational?(): boolean;
  hasPermission?(): boolean;
  isRunning?(): boolean;
  state?: unknown;
}
declare const shizuku: ShizukuApi | undefined;

// --- Java interop (Rhino LiveConnect) -----------------------------------
//
// Referenced via fully-qualified path rather than AutoJs6's importClass()
// shortcut, which binds a short alias into scope in a way TypeScript's
// module system cannot model. The fully-qualified form resolves to the
// identical Java class object, so this is a typing-only difference.

declare namespace org.autojs.autojs.execution {
  class ExecutionConfig {
    setWorkingDirectory(dir: string): void;
  }
}

declare namespace android.app {
  class NotificationChannel {
    constructor(id: string, name: string, importance: number);
    setDescription(description: string): void;
  }

  namespace NotificationManager {
    const IMPORTANCE_HIGH: number;
  }
  interface NotificationManager {
    createNotificationChannel(channel: NotificationChannel): void;
    notify(id: number, notification: unknown): void;
    cancel(id: number): void;
  }

  namespace Notification {
    class Builder {
      constructor(context: unknown, channelId?: string);
      setContentTitle(title: string): Builder;
      setContentText(text: string): Builder;
      setSmallIcon(iconResourceId: number): Builder;
      setOnlyAlertOnce(value: boolean): Builder;
      setAutoCancel(value: boolean): Builder;
      build(): unknown;
    }
  }
}

declare namespace android.R.drawable {
  const ic_dialog_alert: number;
}
