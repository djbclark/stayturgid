# Shizuku UserService is constructed reflectively by the Shizuku server.
-keep class org.stayturgid.agent.ShizukuUserService { *; }
-keepclassmembers class org.stayturgid.agent.ShizukuUserService {
    public <init>();
    public <init>(android.content.Context);
}

# AIDL stubs
-keep class org.stayturgid.agent.IStayTurgidService { *; }
-keep class org.stayturgid.agent.IStayTurgidService$* { *; }

# BouncyCastle (embedded ADB client TLS cert — issue #61). Reflective providers;
# keep and silence the missing-optional-dependency warnings under R8.
-keep class org.bouncycastle.** { *; }
-dontwarn org.bouncycastle.**
-dontwarn javax.naming.**
