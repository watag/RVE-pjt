# A52 outbound GitHub agent

This is an operator-run poller, not a service installed by the repository into
the Android system. The poller, lock, logs, and isolated Git worktrees live in
the Ubuntu proot home under `~/.local/` and `~/.local/state/`, outside the RVE
checkout. Termux:Boot starts it after Android boots; no systemd or inbound SSH
is used.

## What it does

1. Fetches only `origin/main` at a configurable interval (default: 120 seconds).
2. Reads valid task files under `agent/tasks/`; a process-wide file lock
   prevents duplicate runners.
3. Skips a task once its `agent/task-<id>` branch exists on `origin`.
4. Creates an isolated Git worktree from the latest `origin/main` and invokes
   `codex exec --sandbox workspace-write --ask-for-approval never`.
5. Includes the current `AGENTS.md` text in the prompt and instructs Codex not
   to commit, push, switch branches, or write outside the RVE repository.
6. Rejects common credential filenames and high-confidence credential patterns
   before publishing. The runner itself performs commits and pushes with an
   explicit `HEAD:refs/heads/agent/task-<id>` refspec. It has no `main` push
   path.
7. Pushes both success and failure status in
   `agent/results/<id>.md` on the task branch. Logs and Codex output stay on
   the A52. A failed task is reported without publishing partial code edits.

The secret scan is a safety check, not a guarantee that arbitrary sensitive
data can always be recognized. Use a dedicated GitHub credential restricted
to this repository and branch policy; never expose broad credentials to tasks.
Malformed task files with a safe ID in their filename receive a `FAILED`
result; files whose names cannot safely form a branch ID are ignored and logged.

## A52 preparation (before network isolation)

Use Termux from F-Droid or the official Termux source, plus the matching
Termux:Boot app. In Termux, install the proot tools and set up Ubuntu (commands
may differ with the installed Termux version):

```sh
pkg update
pkg install git proot-distro termux-api openssh
proot-distro install ubuntu
```

In Ubuntu proot, install Git and Python, clone RVE, then install Codex CLI and
authenticate it on the A52. Codex CLI publishes a Linux ARM64 build, which is
the expected architecture for the A52. Use the [official Codex CLI
installation instructions](https://github.com/openai/codex#quickstart) and
[authentication guide](https://developers.openai.com/codex/auth) for the current
installer and sign-in flow.

```sh
apt update
apt install -y git python3 ca-certificates
git clone <RVE-GitHub-URL> "$HOME/RVE-pjt"
```

Set up outbound GitHub authentication before isolating the phone. Either use a
dedicated SSH deploy key with write access only to this repository, or HTTPS
with a credential manager. Keep keys/tokens in Termux/Ubuntu's private
credential storage; do not put them in this repository, task files, command
arguments, or logs. If using SSH, verify that outbound SSH works; where port 22
is blocked, configure GitHub SSH over port 443. Test both `git fetch origin`
and a harmless authentication check before relying on the device.

From the Ubuntu proot, install the runner and (if the Termux home is visible)
its boot launcher. The second path is commonly
`/data/data/com.termux/files/home`, but confirm it on the device:

```sh
bash ops/a52-agent/install-proot.sh "$HOME/RVE-pjt" \
  /data/data/com.termux/files/home
```

If the cross-environment path is not accessible, install the runner without
the second argument, then copy `ops/a52-agent/termux-boot.sh` from the Ubuntu
checkout to Termux's `~/.termux/boot/50-rve-agent` and make it executable:

```sh
mkdir -p ~/.termux/boot
cp <path-to-RVE>/ops/a52-agent/termux-boot.sh \
  ~/.termux/boot/50-rve-agent
chmod 700 ~/.termux/boot/50-rve-agent
```

Run a one-shot poll while the network is available:

```sh
"$HOME/.local/bin/rve-agent" --once
```

Check the external log at `~/.local/state/rve-agent/logs/runner.log`. The
installed Codex command must be available as `codex`; override it with the
`RVE_CODEX` environment variable in the external launcher if needed. Confirm
that Codex works non-interactively and that the Linux sandbox can provide
`workspace-write` in this Ubuntu/proot configuration before leaving the device.

## Start, stop, and restart

For foreground/manual use inside Ubuntu:

```sh
"$HOME/.local/bin/rve-agent"
```

For background use, use Termux:Boot: install and open the Termux:Boot app once,
allow Termux to run in the background, and exempt Termux from battery
optimization if Android suspends it. On boot, the launcher takes a Termux wake
lock and starts `proot-distro login ubuntu --shared-tmp` with the runner.
Reboot the phone and confirm the logs advance. Stop manually with Ctrl-C when
running in foreground; for the boot-started instance, locate and stop the
`rve-agent` process inside Ubuntu. `termux-wake-unlock` releases the wake lock
after intentionally stopping the boot-started runner.

The runner is a simple polling loop rather than a systemd unit because Android
and proot do not provide a reliable systemd boot manager. It survives a normal
runner restart: tasks with an already-pushed result branch are skipped, and an
interrupted local task worktree is retained for recovery. Keep the state
directory persistent; deleting it can discard logs and unfinished worktrees.

## Submit and observe a task

Follow [the task format](../../agent/tasks/README.md). Add a new uniquely named
`agent/tasks/<id>.md` file and merge that task commit into `main`. The phone
fetches `main` on the next poll. Do not put credentials or personal data in the
task. A task ID is immutable; submit a new ID to retry a task.

Review `agent/task-<id>` on GitHub:

- Success: the branch contains the implementation and a `SUCCESS` result file.
- Failure: the branch contains a `FAILED` result file without partial code
  changes. Detailed Codex output remains in the A52's external log directory.
- A result branch is a review artifact. Humans review and merge changes into
  `main`; the runner never pushes or merges to `main`.

For one-shot diagnosis, run `rve-agent --once`; for continuous polling, run
`rve-agent`. The default poll interval is two minutes. The runner can be
configured by invoking its Python entry point with `--interval` and `--timeout`.

## Network and isolation

The phone initiates all connections; no PC-to-phone SSH, inbound port, webhook,
or GitHub callback is required. Keep outbound DNS and HTTPS to GitHub available
for Git fetch/push; if GitHub SSH is used, allow the configured SSH endpoint
(port 22 or `ssh.github.com:443`). Codex also needs outbound access to the
OpenAI service used by its configured sign-in/authentication. Therefore a
strict network policy that allows only GitHub will prevent Codex from running;
allow the required OpenAI endpoints as well. The model sandbox's own network
access remains disabled by default in `workspace-write` mode.

Before moving the phone to the `AI-SANDBOX` SSID, verify on that SSID that
GitHub fetch and push plus Codex authentication/API requests work. Android
Wi-Fi isolation may block device-to-device traffic, which is compatible with
this design because the PC does not connect to the A52. The runner does not
depend on LAN DNS, a local webhook, or access from the PC.

## Local checks

The runner uses only the Python standard library. From any Python 3.10+
environment, run:

```sh
python3 -m unittest discover -s ops/a52-agent -p 'test_*.py' -v
python3 -m py_compile ops/a52-agent/runner.py ops/a52-agent/test_runner.py
```
