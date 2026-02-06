from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List

import pygame

from kidbox.config import load_config
from kidbox.ui.common import (
    Button,
    create_fullscreen_window,
    draw_placeholder_icon,
    ignore_system_shortcut,
    is_escape_chord,
    load_image,
    set_env_for_child,
)


@dataclass
class LauncherApp:
    name: str
    icon_path: str
    command: List[str]


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


def _launch_app(app: LauncherApp) -> None:
    if not app.command:
        return
    try:
        child = subprocess.Popen(app.command, env=set_env_for_child())
        child.wait()
    except Exception:
        return


def main() -> None:
    config = load_config()
    apps = _load_apps(config)
    screen, screen_rect = create_fullscreen_window()
    clock = pygame.time.Clock()
    background = (248, 244, 236)

    buttons = _build_buttons(apps, screen_rect)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif is_escape_chord(event):
                pygame.quit()
                sys.exit(0)
            elif ignore_system_shortcut(event):
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for app, button in zip(apps, buttons):
                    if button.hit(event.pos):
                        _launch_app(app)
                        screen, screen_rect = create_fullscreen_window()
                        buttons = _build_buttons(apps, screen_rect)
                        break

        screen.fill(background)
        for app, button in zip(apps, buttons):
            if button.image is None:
                draw_placeholder_icon(screen, button.rect, app.name, border_width=0)
            else:
                button.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
