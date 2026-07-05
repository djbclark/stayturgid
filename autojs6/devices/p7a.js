/** Pixel 7a device profile */
module.exports = {
    id: "p7a",
    label: "Pixel 7a",
    shizukuPackage: "moe.shizuku.privileged.api",
    shizukuActivity: "moe.shizuku.manager.MainActivity",
    // Fallback tap if text-based find fails (1080x2400, scroll to wireless-debug section)
    shizukuStartCoords: { x: 227, y: 1992 },
    tailscaleIp: "100.65.230.108",
    tailscalePackage: "com.tailscale.ipn",
    tailscaleActivity: "com.tailscale.ipn.MainActivity",
    notifyTag: "(7a)",
};
