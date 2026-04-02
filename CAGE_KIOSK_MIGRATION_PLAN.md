# ToddlerBox Cage-Default Boot Migration Plan

## Objective
Move ToddlerBox from "GNOME autostart app" to "Cage-first kiosk session" so top-edge shell gestures are no longer a failure mode, while preserving a parent-only escape chord (`Ctrl+Alt+Home`) that can intentionally exit to either:

- `tty` (parent shell on the kiosk box), or
- Ubuntu GNOME desktop session.

This document is an implementation plan, not a completed migration.

## Current State (Baseline)
- Launch path is GNOME autostart (`~/.config/autostart/toddlerbox-launcher.desktop`) running `scripts/run-stable.sh`.
- Launcher exits on escape chord via `sys.exit(0)` in `src/toddlerbox/launcher.py`.
- Escape chord detection is `Ctrl+Alt+Home` in `src/toddlerbox/ui/common.py` (`is_escape_chord`).
- Existing docs describe "escape reveals GNOME" (`README.md`, `toddlerbox_design_contract.md`).

## Target End State
- System boots directly into Cage running ToddlerBox launcher (not GNOME shell).
- ToddlerBox remains fullscreen/touch-first with no shell chrome.
- Escape chord remains hidden and parent-only.
- Escape behavior is explicitly configurable:
  - `tty`: close ToddlerBox/Cage and return to `tty1` shell.
  - `gnome`: close ToddlerBox/Cage and launch Ubuntu GNOME session.
- Startup and recovery are deterministic and documented.

## Recommended Architecture
Use a `tty1` autologin kiosk bootstrap as the default path:

1. Machine boots to `multi-user.target`.
2. `tty1` autologins kiosk user.
3. User login shell starts a repo script (e.g. `scripts/kiosk-session.sh`).
4. Script launches Cage and `scripts/run-stable.sh`.
5. Launcher escape chord exits with a dedicated code.
6. Wrapper script maps that code to `tty` or `gnome` action.

Reason: this cleanly supports both requested parent exits (`tty` and `gnome`) without depending on GNOME shell behavior during normal child use.

## Phase 0: Preconditions and Safety
1. Snapshot current machine config before changing boot/session behavior.
2. Record current defaults:
   - `systemctl get-default`
   - `/etc/gdm3/custom.conf` (if present)
   - existing `~/.config/autostart/toddlerbox-launcher.desktop`
3. Keep a rollback path ready (documented in Phase 8).
4. Confirm local input devices and touch work in current ToddlerBox build.

## Phase 1: Code Prep in ToddlerBox
### 1.1 Add explicit escape outcome contract
Current launcher exits with generic `0`; this is ambiguous (clean quit vs parent escape). Add a dedicated escape exit signal.

Implementation tasks:
1. Define constants (example):
   - `PARENT_ESCAPE_EXIT_CODE = 86`
   - optional `NORMAL_EXIT_CODE = 0`
2. In `src/toddlerbox/launcher.py`, on `is_escape_chord(event)`, call `pygame.quit()` then `sys.exit(PARENT_ESCAPE_EXIT_CODE)`.
3. Keep existing behavior unchanged for non-chord exits.

### 1.2 Add config knobs for parent escape target
Introduce config for parent exit routing:

```yaml
system:
  parent_escape_action: tty   # tty | gnome
```

Implementation tasks:
1. Extend `DEFAULT_CONFIG` in `src/toddlerbox/config.py` with `system.parent_escape_action` defaulting to `tty`.
2. Add a small helper (new module or launcher-local) to validate allowed actions.
3. Log selected action at launcher start for observability.

### 1.3 Keep design contract aligned
Update docs after implementation:
1. `README.md` deployment section: GNOME autostart no longer primary default.
2. `toddlerbox_design_contract.md`: change "escape reveals GNOME" to "escape follows configured parent action".

## Phase 2: Test Prep in Repo
Add unit coverage so escape behavior is durable.

Implementation tasks:
1. `tests/test_launcher.py`
   - Assert escape chord leads to parent escape exit code.
2. `tests/test_config.py` (or existing config tests)
   - Assert default `system.parent_escape_action == "tty"`.
   - Assert override from YAML works for `gnome`.
3. Optional:
   - Validate invalid values fall back safely to `tty`.

## Phase 3: Add Kiosk Session Scripts (Repo)
Create scripts to avoid manual shell glue.

### 3.1 `scripts/run-cage.sh`
Purpose: one command to run ToddlerBox inside Cage.

Expected behavior:
1. Ensure repo root / venv assumptions match `scripts/run-stable.sh`.
2. Start cage with single client mode:
   - `cage -- ./scripts/run-stable.sh`
3. Exit with child exit status.

### 3.2 `scripts/kiosk-session.sh`
Purpose: parent wrapper that interprets escape exit code and routes to selected action.

Pseudo-flow:
1. Load `system.parent_escape_action` from ToddlerBox config (or env var fallback).
2. Run Cage + launcher.
3. Branch on exit code:
   - `86`: parent escape requested.
   - other non-zero: crash path; restart/backoff or return shell.
4. If action `tty`: return to shell (`exit 0`).
5. If action `gnome`: `exec dbus-run-session gnome-session --session=ubuntu`.

Notes:
- Keep script idempotent and log to stdout + `data/logs`.
- Keep dependencies minimal; avoid introducing desktop-specific assumptions beyond explicit `gnome` branch.

## Phase 4: Machine Install Plan (Cage + Runtime)
Install packages and verify stack.

Packages (Ubuntu):
1. `cage`
2. `libinput-tools` (optional diagnostics)
3. Existing Python/uv deps already used by ToddlerBox.

Validation commands:
1. `cage --version`
2. `uv run python -m toddlerbox.launcher`
3. `cage -- ./scripts/run-stable.sh` (manual smoke test from tty)

## Phase 5: Make Cage the Default Boot Experience
### 5.1 Switch default target to text boot
1. `sudo systemctl set-default multi-user.target`
2. Disable GDM for default boot path:
   - `sudo systemctl disable gdm` (or `gdm3` depending on package naming)

### 5.2 Configure `tty1` autologin for kiosk user
1. Create override:
   - `/etc/systemd/system/getty@tty1.service.d/autologin.conf`
2. Set ExecStart equivalent to:
   - `/sbin/agetty --autologin <kiosk_user> --noclear %I $TERM`
3. `sudo systemctl daemon-reload`
4. `sudo systemctl restart getty@tty1`

### 5.3 Autostart kiosk session from login shell
In kiosk user shell init (prefer `~/.profile` or `~/.bash_profile`):
1. Guard for `tty1` and non-SSH.
2. Guard against recursive relaunch.
3. `exec /home/<user>/git/ToddlerBox/scripts/kiosk-session.sh`

## Phase 6: Parent Escape Routing
Implement and validate both routes.

### Option A: Exit to `tty` (recommended default)
Behavior after `Ctrl+Alt+Home`:
1. Launcher exits with code `86`.
2. `kiosk-session.sh` detects code and action `tty`.
3. Script exits to shell prompt on `tty1`.

### Option B: Exit to Ubuntu GNOME
Behavior after `Ctrl+Alt+Home`:
1. Launcher exits with code `86`.
2. `kiosk-session.sh` detects action `gnome`.
3. Script runs `exec dbus-run-session gnome-session --session=ubuntu`.

If direct `gnome-session` start is unreliable on this machine, fallback implementation:
1. Start display manager explicitly (`sudo systemctl start gdm`/`gdm3`) from a privileged helper.
2. Hand off to GNOME login/autologin path.

## Phase 7: Hardening and Operational Guardrails
1. Keep `scripts/noop_keys_keyd.sh` for hardware key hardening (`Super`, media, etc.).
2. Verify touch still works in Cage (tap/drag in launcher + apps).
3. Ensure no child-facing error UI; log failures only.
4. Add a short operator runbook:
   - how to temporarily bypass kiosk at boot,
   - how to recover if Cage fails,
   - where logs are located.

## Phase 8: Rollback Plan
If kiosk migration fails, recover to original GNOME autostart deployment.

Rollback steps:
1. `sudo systemctl set-default graphical.target`
2. `sudo systemctl enable gdm` (or `gdm3`)
3. Remove/disable `getty@tty1` autologin override.
4. Re-enable prior `~/.config/autostart/toddlerbox-launcher.desktop` behavior.
5. Reboot and verify GNOME autologin + ToddlerBox autostart returns.

## Verification Checklist (Done = Migration Complete)
1. Cold boot lands in ToddlerBox under Cage without GNOME shell visible.
2. Top-edge swipe no longer exposes overview/window controls.
3. Touch works in launcher, paint, photos, typing.
4. Escape chord works only from keyboard: `Ctrl+Alt+Home`.
5. With `parent_escape_action=tty`, chord returns to `tty1` shell.
6. With `parent_escape_action=gnome`, chord launches Ubuntu GNOME session.
7. Crash recovery still functions (`scripts/run-stable.sh` backoff/restart).
8. Docs updated and consistent across `README.md` + design contract.

## Suggested File Changes (When You Execute This Plan)
Repo files likely to change:
1. `src/toddlerbox/launcher.py`
2. `src/toddlerbox/config.py`
3. `config.yaml`
4. `scripts/run-cage.sh` (new)
5. `scripts/kiosk-session.sh` (new)
6. `tests/test_launcher.py`
7. `tests/test_config.py` (or existing config test file)
8. `README.md`
9. `toddlerbox_design_contract.md`

Machine files likely to change:
1. `/etc/systemd/system/getty@tty1.service.d/autologin.conf`
2. kiosk user `~/.profile` or `~/.bash_profile`
3. system default target (`multi-user.target`)
4. optionally GDM service state and config

## Sequencing Recommendation
1. Complete Phase 1-3 in repo + tests first.
2. Validate locally by launching `scripts/kiosk-session.sh` manually from tty.
3. Only then apply Phase 5 boot-target/autologin changes.
4. Validate both parent-exit modes before considering migration done.
