#!/data/data/com.termux/files/usr/bin/bash
set -eu

# This script runs in Termux (Android), not in Ubuntu/proot.
DISTRO=${RVE_PROOT_DISTRO:-ubuntu}
mkdir -p "$HOME/.termux/boot"
termux-wake-lock
nohup proot-distro login "$DISTRO" --shared-tmp -- bash -lc \
  'exec "$HOME/.local/bin/rve-agent"' \
  >>"$HOME/.termux/boot/rve-agent-boot.log" 2>&1 </dev/null &
