# Shizuku UserService is constructed reflectively by the Shizuku server.
-keep class org.stayturgid.agent.ShizukuUserService { *; }
-keepclassmembers class org.stayturgid.agent.ShizukuUserService {
    public <init>();
    public <init>(android.content.Context);
}

# AIDL stubs
-keep class org.stayturgid.agent.IStayTurgidService { *; }
-keep class org.stayturgid.agent.IStayTurgidService$* { *; }
