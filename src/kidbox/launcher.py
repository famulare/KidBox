from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import pygame

from kidbox.config import load_config
from kidbox.paint.app import run_embedded as run_paint_embedded
from kidbox.photos.app import run_embedded as run_photos_embedded
from kidbox.typing.app import run_embedded as run_typing_embedded
from kidbox.ui.common import (
    Button,
    create_fullscreen_window,
    draw_placeholder_icon,
    ignore_system_shortcut,
    is_primary_pointer_event,
    is_escape_chord,
    load_image,
    pointer_event_pos,
    set_env_for_child,
)


@dataclass
class LauncherApp:
    name: str
    icon_path: str
    command: List[str]


_EMBEDDED_RUNNERS: Dict[str, Callable[[pygame.Surface, pygame.Rect, pygame.time.Clock], None]] = {
    "kidbox.paint": run_paint_embedded,
    "kidbox.photos": run_photos_embedded,
    "kidbox.typing": run_typing_embedded,
}


def _parse_command(cmd: Any) -> List[str]:
    if isinstance(cmd, list):
        return [str(part) for part in cmd]
    if isinstance(cmd, str):
        return shlex.split(cmd)
    return []


def _load_apps(config: Dict[str, Any]) -> List[LauncherApp]:
    apps = []
    for app in config.get("launcher", {}).get("apps", []):
        apps.append(
            LauncherApp(
                name=str(app.get("name", "App")),
                icon_path=str(app.get("icon_path", "")),
                command=_parse_command(app.get("command", "")),
            )
        )
    return apps


def _resolve_command(command: List[str]) -> List[str]:
    if not command:
        return []
    executable = command[0]
    if executable not in {"python", "python3"}:
        return command
    interpreter = sys.executable or shutil.which("python3") or shutil.which("python")
    if interpreter:
        return [interpreter, *command[1:]]
    return command


def _embedded_runner_for_command(command: List[str]) -> Optional[Callable[[pygame.Surface, pygame.Rect, pygame.time.Clock], None]]:
    if "-m" not in command:
        return None
    idx = command.index("-m")
    if idx + 1 >= len(command):
        return None
    module_name = command[idx + 1]
    return _EMBEDDED_RUNNERS.get(module_name)


def _build_buttons(apps: List[LauncherApp], screen_rect: pygame.Rect) -> List[Button]:
    icon_size = max(120, int(min(screen_rect.width, screen_rect.height) * 0.18))
    gap = int(icon_size * 0.3)
    total_width = icon_size * len(apps) + gap * (len(apps) - 1)
    start_x = screen_rect.centerx - total_width // 2
    y = screen_rect.centery - icon_size // 2
    buttons = []
    for idx, app in enumerate(apps):
        rect = pygame.Rect(start_x + idx * (icon_size + gap), y, icon_size, icon_size)
        image = load_image(app.icon_path, (icon_size, icon_size))
        buttons.append(
            Button(
                rect=rect,
                label=app.name,
                image=image,
                fill=(245, 245, 245),
                border_width=0,
            )
        )
    return buttons


def _launch_app(app: LauncherApp, screen: pygame.Surface, screen_rect: pygame.Rect, clock: pygame.time.Clock) -> bool:
    runner = _embedded_runner_for_command(app.command)
    if runner is not None:
        try:
            runner(screen, screen_rect, clock)
        except Exception:
            return False
        return False

    command = _resolve_command(app.command)
    if not command:
        return False
    try:
        child = subprocess.Popen(
            command,
            env=set_env_for_child(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child.wait()
    except Exception:
        return False
    return True


def _restore_launcher_window() -> tuple[pygame.Surface, pygame.Rect]:
    existing = pygame.display.get_surface()
    if existing is not None:
        return existing, existing.get_rect()
    return create_fullscreen_window()


def _draw_launcher_frame(
    screen: pygame.Surface,
    background: tuple[int, int, int],
    apps: List[LauncherApp],
    buttons: List[Button],
) -> None:
    screen.fill(background)
    for app, button in zip(apps, buttons):
        if button.image is None:
            draw_placeholder_icon(screen, button.rect, app.name, border_width=0)
        else:
            button.draw(screen)
    pygame.display.flip()


def main() -> None:
    config = load_config()
    apps = _load_apps(config)
    screen, screen_rect = create_fullscreen_window()
    clock = pygame.time.Clock()
    background = (248, 244, 236)

    buttons = _build_buttons(apps, screen_rect)
    pointer_block_until = 0.0

    running = True
    _draw_launcher_frame(screen, background, apps, buttons)
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif is_escape_chord(event):
                pygame.quit()
                sys.exit(0)
            elif ignore_system_shortcut(event):
                continue
            elif is_primary_pointer_event(event, is_down=True):
                if time.monotonic() < pointer_block_until:
                    continue
                pos = pointer_event_pos(event, screen_rect)
                if pos is None:
                    continue
                for app, button in zip(apps, buttons):
                    if button.hit(pos):
                        used_subprocess = _launch_app(app, screen, screen_rect, clock)
                        if used_subprocess:
                            screen, screen_rect = _restore_launcher_window()
                            buttons = _build_buttons(apps, screen_rect)
                        pointer_events = [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP]
                        finger_down = getattr(pygame, "FINGERDOWN", None)
                        finger_up = getattr(pygame, "FINGERUP", None)
                        if finger_down is not None:
                            pointer_events.append(finger_down)
                        if finger_up is not None:
                            pointer_events.append(finger_up)
                        pygame.event.clear(pointer_events)
                        pointer_block_until = time.monotonic() + 0.25
                        _draw_launcher_frame(screen, background, apps, buttons)
                        break

        _draw_launcher_frame(screen, background, apps, buttons)
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
