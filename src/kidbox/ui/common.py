from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pygame


Color = Tuple[int, int, int]


@dataclass
class Button:
    rect: pygame.Rect
    label: str = ""
    image: Optional[pygame.Surface] = None
    fill: Optional[Color] = None
    border_color: Color = (30, 30, 30)

    def draw(self, surface: pygame.Surface, font: Optional[pygame.font.Font] = None) -> None:
        if self.fill is not None:
            pygame.draw.rect(surface, self.fill, self.rect, border_radius=12)
        if self.image is not None:
            image_rect = self.image.get_rect(center=self.rect.center)
            surface.blit(self.image, image_rect)
        pygame.draw.rect(surface, self.border_color, self.rect, width=2, border_radius=12)
        if self.label and font is not None:
            text = font.render(self.label, True, (20, 20, 20))
            text_rect = text.get_rect(center=(self.rect.centerx, self.rect.bottom - 18))
            surface.blit(text, text_rect)

    def hit(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


def create_fullscreen_window() -> Tuple[pygame.Surface, pygame.Rect]:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.mouse.set_visible(True)
    return screen, screen.get_rect()


def load_image(path: str, size: Optional[Tuple[int, int]] = None) -> Optional[pygame.Surface]:
    if not path:
        return None
    resolved = Path(path)
    if not resolved.exists():
        return None
    image = pygame.image.load(str(resolved)).convert_alpha()
    if size:
        image = pygame.transform.smoothscale(image, size)
    return image


def draw_placeholder_icon(surface: pygame.Surface, rect: pygame.Rect, label: str) -> None:
    pygame.draw.rect(surface, (220, 220, 220), rect, border_radius=16)
    pygame.draw.rect(surface, (40, 40, 40), rect, width=3, border_radius=16)
    font = pygame.font.SysFont("sans", 22)
    text = font.render(label, True, (30, 30, 30))
    text_rect = text.get_rect(center=rect.center)
    surface.blit(text, text_rect)


def draw_home_button(surface: pygame.Surface, rect: pygame.Rect) -> None:
    pygame.draw.rect(surface, (240, 240, 240), rect, border_radius=10)
    pygame.draw.rect(surface, (30, 30, 30), rect, width=2, border_radius=10)
    roof = [
        (rect.centerx, rect.top + 8),
        (rect.left + 8, rect.centery),
        (rect.right - 8, rect.centery),
    ]
    pygame.draw.polygon(surface, (50, 50, 50), roof)
    body = pygame.Rect(rect.left + 12, rect.centery, rect.width - 24, rect.height - 16)
    pygame.draw.rect(surface, (50, 50, 50), body, width=2)


def is_escape_chord(event: pygame.event.Event) -> bool:
    if event.type != pygame.KEYDOWN:
        return False
    if event.key != pygame.K_HOME:
        return False
    mods = event.mod
    required = pygame.KMOD_CTRL | pygame.KMOD_ALT
    disallowed = pygame.KMOD_SHIFT | pygame.KMOD_META | pygame.KMOD_GUI | pygame.KMOD_ALTGR
    return (mods & required) == required and (mods & disallowed) == 0


def ignore_system_shortcut(event: pygame.event.Event) -> bool:
    if event.type != pygame.KEYDOWN:
        return False
    if event.key in {
        pygame.K_F1,
        pygame.K_F2,
        pygame.K_F3,
        pygame.K_F4,
        pygame.K_F5,
        pygame.K_F6,
        pygame.K_F7,
        pygame.K_F8,
        pygame.K_F9,
        pygame.K_F10,
        pygame.K_F11,
        pygame.K_F12,
    }:
        return True
    return False


def set_env_for_child() -> dict:
    env = os.environ.copy()
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    return env
