/** Galaxy S24 (SM-S921U1) device profile */
module.exports = {
    id: "s24",
    label: "Galaxy S24",
    shizukuPackage: "moe.shizuku.privileged.api",
    shizukuActivity: "moe.shizuku.manager.MainActivity",
    // Fallback tap (1080x2340-ish, scroll to top of wireless-debug section)
    shizukuStartCoords: { x: 227, y: 1977 },
    tailscaleIp: "100.123.218.30",
    notifyTag: "(S24)",
    // Samsung: secure-setting writes cannot enable the wireless-debugging service;
    // UI toggle is the fallback when Shizuku alone is insufficient.
    samsungWirelessDebugFallback: true,
};
