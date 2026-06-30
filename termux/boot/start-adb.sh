#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot script — runs on every boot after first unlock
# Deploy to: ~/.termux/boot/start-adb.sh on device

# Start SSH server so the device is reachable via ADB port-forward
sshd

# Wait for WiFi/network to settle
sleep 30

# Belt-and-suspenders: attempt to open ADB TCP port.
# Shizuku TCP mode (the primary mechanism) usually beats this to it.
adb connect 127.0.0.1:5555 || true
adb tcpip 5555 || true
