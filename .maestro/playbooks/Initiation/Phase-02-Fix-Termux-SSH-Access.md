# Phase 02: Fix Termux SSH Access

SSH into the Termux environment on the Pixel 7a currently fails (key auth rejected). This phase regenerates a fresh ed25519 key pair on the Mac and installs the public key directly into Termux's `authorized_keys` via ADB shell — bypassing the broken key rather than debugging it. By the end, passwordless SSH from the Mac into Termux works, which is required for the recovery script deployment in the next phase.

## Tasks

- [ ] Generate a fresh ed25519 SSH key pair dedicated to this device. Run `ssh-keygen -t ed25519 -f ~/.ssh/termux_key -N ""` on the Mac. Confirm both `~/.ssh/termux_key` and `~/.ssh/termux_key.pub` exist with `ls -la ~/.ssh/termux_key*`.

- [ ] Push the new public key to the device via ADB. Run `adb -s 35261JEHN12374 push ~/.ssh/termux_key.pub /sdcard/termux_authorized_key` and confirm with `adb -s 35261JEHN12374 shell ls -la /sdcard/termux_authorized_key`.

- [ ] Install the key into Termux's authorized_keys via ADB shell, creating the `.ssh` directory if needed and setting correct permissions:
  - `adb -s 35261JEHN12374 shell "mkdir -p /data/data/com.termux/files/home/.ssh"`
  - `adb -s 35261JEHN12374 shell "cat /sdcard/termux_authorized_key >> /data/data/com.termux/files/home/.ssh/authorized_keys"`
  - `adb -s 35261JEHN12374 shell "chmod 700 /data/data/com.termux/files/home/.ssh && chmod 600 /data/data/com.termux/files/home/.ssh/authorized_keys"`
  Verify by reading the file back: `adb -s 35261JEHN12374 shell "cat /data/data/com.termux/files/home/.ssh/authorized_keys"` should show the same public key content as `~/.ssh/termux_key.pub`.

- [ ] Test the SSH connection from the Mac using the new key: `ssh -i ~/.ssh/termux_key -p 8022 -o StrictHostKeyChecking=accept-new u0_a590@192.168.68.59 echo SSH_OK`. Expected output: `SSH_OK`. If the connection is refused entirely (not a key rejection), confirm the Termux `sshd` service is running on-device via `adb -s 35261JEHN12374 shell "pgrep -f sshd"` and instruct starting it with `sshd` inside a Termux terminal session if absent.

- [ ] Once the raw IP connection works, add a convenience SSH config entry so later phases can use the short hostname. Append to `~/.ssh/config`:
  ```
  Host pixel7a-termux
    HostName 192.168.68.59
    Port 8022
    User u0_a590
    IdentityFile ~/.ssh/termux_key
  ```
  Verify with `ssh pixel7a-termux echo CONFIG_OK` — expected output: `CONFIG_OK`.
