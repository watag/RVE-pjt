#!/usr/bin/env bash
set -euo pipefail

# Run inside the Ubuntu proot. Optional second argument is Termux's home path,
# visible from the proot (usually /data/data/com.termux/files/home).
repo_path=${1:-}
termux_home=${2:-}
if [[ -z "$repo_path" || ! -f "$repo_path/AGENTS.md" || ! -d "$repo_path/.git" ]]; then
  echo "Usage: $0 /absolute/path/to/RVE-checkout [termux-home-visible-in-proot]" >&2
  exit 2
fi
repo_path=$(cd "$repo_path" && pwd -P)

install_root="$HOME/.local/libexec/rve-agent"
bin_root="$HOME/.local/bin"
state_root="$HOME/.local/state/rve-agent"
mkdir -p "$install_root" "$bin_root" "$state_root"
install -m 0644 "$(dirname "$0")/runner.py" "$install_root/runner.py"

cat > "$bin_root/rve-agent" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$install_root/runner.py" --repo "$repo_path" --state-dir "$state_root" "\$@"
EOF
chmod 0755 "$bin_root/rve-agent"

if [[ -n "$termux_home" ]]; then
  termux_home=$(realpath -m "$termux_home")
  boot_dir="$termux_home/.termux/boot"
  mkdir -p "$boot_dir"
  install -m 0755 "$(dirname "$0")/termux-boot.sh" "$boot_dir/50-rve-agent"
  echo "Installed Termux:Boot launcher at $boot_dir/50-rve-agent"
else
  echo "Runner installed. Copy ops/a52-agent/termux-boot.sh to Termux ~/.termux/boot/50-rve-agent."
fi

echo "Installed external runner at $install_root"
echo "Runner state and logs are outside the repository at $state_root"
echo "Run once to verify: $bin_root/rve-agent --once"
