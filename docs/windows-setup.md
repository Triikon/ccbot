# Windows setup

CCBot works on Windows 10/11 against [`psmux`](https://github.com/psmux/psmux),
the Windows-native tmux clone (no WSL/Cygwin/MSYS2 needed). The libtmux
compatibility shim that makes this work ships with ccbot
(`src/ccbot/_compat.py`) and is applied automatically at import — no extra
flags or env vars.

This document walks through a fresh setup end-to-end and covers
Windows-specific operational concerns.

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| **psmux** | Native Windows tmux | `winget install marlocarlo.psmux` |
| **Python 3.12+** | ccbot runtime | `winget install Python.Python.3.12` |
| **uv** (recommended) | Python tool/venv manager | `winget install astral-sh.uv` |
| **Claude Code CLI** | The agent ccbot wraps | Follow Anthropic docs |
| **Telegram supergroup with Forum Topics enabled** | ccbot's UX model — one topic per Claude session | See "Telegram configuration" below |

After installing psmux, open a fresh PowerShell window so its install location
is on `PATH`. Verify with `tmux -V` (psmux ships `tmux`, `psmux`, and `pmux`
aliases).

## Telegram configuration

CCBot does **not** work in direct messages — it relies on
`message_thread_id` from supergroup forum topics. Configuring this is the
single most common source of "the bot doesn't respond" reports.

1. **Create the bot** via [@BotFather](https://t.me/BotFather): `/newbot`,
   answer prompts, save the bot token.
2. **Disable Group Privacy** on the bot: in @BotFather → `/mybots` → pick
   your bot → **Bot Settings** → **Group Privacy** → **Turn off**. Without
   this, the bot only sees `/commands` in groups, not regular messages.
3. **Create a Telegram group** (any client) — name it whatever you want; you
   can be the only member.
4. **Enable Topics** on the group: open the group → tap the name at the top
   → Edit → toggle **Topics** on. Telegram converts the group to a
   supergroup.
5. **Add the bot** to the group as a member, then **promote it to admin**
   (default admin permissions are fine).
6. **Get your Telegram user ID** by messaging
   [@userinfobot](https://t.me/userinfobot) — it replies with your numeric
   `Id`. Save this; it goes into `ALLOWED_USERS`.

When everything is configured, sending any message in a topic should prompt
ccbot with a directory browser (when no Claude session is yet bound to that
topic).

## Install ccbot

```powershell
uv tool install git+https://github.com/Triikon/ccbot.git
```

Verify with `ccbot --help`.

Then create `~/.ccbot/.env` (path resolves to
`C:\Users\<you>\.ccbot\.env`):

```ini
TELEGRAM_BOT_TOKEN=<your-bot-token>
ALLOWED_USERS=<your-telegram-user-id>
# Optional, for voice transcription:
# OPENAI_API_KEY=...
```

Lock down the file ACL so the token isn't readable by other users on the
machine:

```powershell
icacls "$HOME\.ccbot\.env" /inheritance:r /grant:r "$($env:USERNAME):F" "SYSTEM:F"
```

## Install the SessionStart hook

ccbot needs Claude Code to fire a `SessionStart` hook so it can map tmux
windows to Claude session IDs. The simplest way:

```powershell
ccbot hook --install
```

This edits `~/.claude/settings.json` to add a `SessionStart` hook that
invokes `ccbot hook`. If you already have hooks defined there, it merges
non-destructively.

## Run ccbot

For a one-off test:

```powershell
ccbot
```

You should see `Tmux session 'ccbot' ready` and `Starting Telegram bot...`.
From your Telegram group, send a message in a topic — ccbot prompts the
directory browser, you pick a project directory, Claude launches in a tmux
window, and you can talk to it from Telegram.

## Run ccbot at logon (Scheduled Task)

For a persistent setup that survives reboots, register a Scheduled Task. The
wrapper script captures stdout/stderr to a rolling log under `~/.ccbot`.

Save this to `~/.ccbot/run-ccbot.ps1`:

```powershell
# Runs ccbot with stdout/stderr captured to a rolling log.
$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'

# Set the cwd that ccbot's directory browser opens at.
if (Test-Path 'C:\AIProjects') { Set-Location 'C:\AIProjects' }

$logDir = Join-Path $HOME '.ccbot'
$logFile = Join-Path $logDir ('ccbot-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

# Trim old logs (keep last 5).
Get-ChildItem $logDir -Filter 'ccbot-*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 5 |
    Remove-Item -Force -ErrorAction SilentlyContinue

& "$HOME\.local\bin\ccbot.exe" *>&1 |
    Out-File -FilePath $logFile -Encoding utf8 -Append
```

Register the Scheduled Task:

```powershell
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument '-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File C:\Users\<you>\.ccbot\run-ccbot.ps1'

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName 'ccbot' `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal
```

Replace `<you>` with your username. Start it now without rebooting:

```powershell
Start-ScheduledTask -TaskName 'ccbot'
```

Verify it's running: `Get-Process ccbot`.

The browse-root for ccbot's directory picker is determined by the `cwd` of
the running ccbot process. The wrapper above sets it to `C:\AIProjects`;
edit that line to point wherever your projects live.

## Operational notes

### Attaching locally to running sessions

ccbot manages its own tmux session named `ccbot`. To attach from PowerShell
and watch/interact alongside the Telegram side:

```powershell
tmux attach -t ccbot
```

Each Claude session ccbot starts shows up as a separate window in that
session. `Ctrl-b w` for the window picker, `Ctrl-b d` to detach (Telegram
keeps controlling — nothing is killed).

Both local terminal and Telegram can be attached simultaneously and input
mirrors. Add `-d` to kick the other client off (`tmux attach -d -t ccbot`).

### Log location

Scheduled-task runs log to `~/.ccbot/ccbot-<timestamp>.log`. The wrapper
keeps the last 5 logs and prunes older ones.

### Troubleshooting

**Bot replies "No session bound to this topic"** — you're in a direct
message instead of a supergroup topic. Re-read "Telegram configuration"
above. The bot only works in supergroups with Topics enabled, and must be
an admin with Group Privacy off.

**Old inline-keyboard buttons crash ccbot** — Telegram invalidates
callback queries after ~5 minutes. Tapping an old "Approve" or "Pick
directory" button from earlier in chat history raises
`telegram.error.BadRequest: Query is too old`, which (in the current
version of `python-telegram-bot`) escapes the bot's error handler and
kills the process. The Scheduled Task restarts ccbot on the next reboot
but not mid-session. **Always interact with the most recent message.**

**Directory browser shows Windows system folders** — ccbot's browser starts
at `Path.cwd()` of the ccbot process. Either change the Scheduled Task
wrapper's `Set-Location` line, or set the task's "Start in" directory to
something sensible.

**Permission denied or missing files** — psmux requires PowerShell 5.1+
(works with both Windows PowerShell and pwsh 7). The first time you call
`tmux` after installing psmux, you may need to open a fresh PowerShell
window for the User PATH update to take effect.

### Compatibility shim

`src/ccbot/_compat.py` monkey-patches three issues in libtmux that surface
on Windows + psmux:

1. Forcing `encoding='utf-8'` on libtmux's subprocess pipes (Windows
   defaults to cp1252, which mangles psmux's UTF-8 format-separator output).
2. Relaxing `parse_output`'s strict zip and stripping psmux's occasional
   leading separator.
3. Rewriting libtmux's joined `-c<path>` start-directory arg into split
   `-c <path>` form (psmux ignores the joined form).

These are applied automatically at `import ccbot` time and are no-ops on
Linux/macOS where the underlying tmux already behaves correctly. Once these
fixes land in libtmux upstream, the shim can be removed.
