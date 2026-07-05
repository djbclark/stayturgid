#!/data/data/com.termux/files/usr/bin/bash
# Optional Termux:Boot companion for AutoJs6 mode — fast repair trigger listener.
# Deploy to ~/.termux/boot/start-repair-bridge.sh when using autojs6/ stack.
# Coexists with start-adb.sh; does not replace it.

export PATH=/data/data/com.termux/files/usr/bin:$PATH
export HOME=/data/data/com.termux/files/home

if [[ -x "$HOME/repair-bridge.sh" ]] && ! pgrep -f repair-bridge.sh >/dev/null 2>&1; then
    nohup "$HOME/repair-bridge.sh" >> "$HOME/.repair-bridge.log" 2>&1 &
fi
