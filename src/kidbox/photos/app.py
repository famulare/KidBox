from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pygame

from kidbox.config import load_config
from kidbox.paths import ensure_directories, get_data_root
from kidbox.ui.common import Button, create_fullscreen_window, draw_home_button


@dataclass
class PhotoItem:
    path: Path
    thumb: Optional[pygame.Surface] = None


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


def _thumb_name(path: Path) -> str:
    suffix = path.suffix.lower().replace(".", "")
    return f"{path.stem}_{suffix}.png"


def _scale_to_fit(surface: pygame.Surface, size: Tuple[int, int]) -> pygame.Surface:
    target_w, target_h = size
    src_w, src_h = surface.get_size()
    scale = min(target_w / src_w, target_h / src_h)
    new_size = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    return pygame.transform.smoothscale(surface, new_size)


class PhotosApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.data_root = get_data_root(self.config)
        dirs = ensure_directories(self.data_root)
        self.photos_dir = dirs["photos"]
        self.library_dir = self.photos_dir / "library"
        self.thumb_dir = self.photos_dir / "thumbs"

        self.screen, self.screen_rect = create_fullscreen_window()
        self.clock = pygame.time.Clock()

        base_strip_width = max(160, int(self.screen_rect.width * 0.25))
        self.strip_width = max(112, int(base_strip_width * 0.7))
        self.strip_rect = pygame.Rect(
            self.screen_rect.width - self.strip_width,
            0,
            self.strip_width,
            self.screen_rect.height,
        )
        self.main_rect = pygame.Rect(0, 0, self.screen_rect.width - self.strip_width, self.screen_rect.height)

        self.thumb_size = self.strip_width - 24
        self.thumb_gap = 14
        self.scroll_y = 0

        self.items = [PhotoItem(path) for path in sorted(self.library_dir.iterdir()) if _is_image(path)]
        self.current_index = 0
        self.current_image: Optional[pygame.Surface] = None
        self._ensure_thumbnails()
        self._load_current_image()

        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_delta: Tuple[int, int] = (0, 0)
        self.strip_drag_last_y: Optional[int] = None
        self.show_arrows = bool(self.config.get("photos", {}).get("show_arrows", False))
        self.font = pygame.font.SysFont("sans", 18)

        self.home_button = Button(rect=pygame.Rect(20, 20, 70, 50), fill=(240, 240, 240))
        self.left_arrow = Button(rect=pygame.Rect(20, self.screen_rect.centery - 30, 50, 60), fill=(245, 245, 245))
        self.right_arrow = Button(
            rect=pygame.Rect(self.main_rect.right - 70, self.screen_rect.centery - 30, 50, 60),
            fill=(245, 245, 245),
        )

    def _ensure_thumbnails(self) -> None:
        for item in self.items:
            thumb_path = self.thumb_dir / _thumb_name(item.path)
            source_mtime = item.path.stat().st_mtime
            if thumb_path.exists() and thumb_path.stat().st_mtime >= source_mtime:
                try:
                    item.thumb = pygame.image.load(str(thumb_path)).convert_alpha()
                    continue
                except Exception:
                    pass
            try:
                image = pygame.image.load(str(item.path)).convert_alpha()
                thumb = _scale_to_fit(image, (self.thumb_size, self.thumb_size))
                pygame.image.save(thumb, str(thumb_path))
                item.thumb = thumb
            except Exception:
                item.thumb = None

    def _load_current_image(self) -> None:
        if not self.items:
            self.current_image = None
            return
        path = self.items[self.current_index].path
        try:
            image = pygame.image.load(str(path)).convert_alpha()
            self.current_image = _scale_to_fit(image, self.main_rect.size)
        except Exception:
            self.current_image = None

    def _change_index(self, delta: int) -> None:
        if not self.items:
            return
        self.current_index = (self.current_index + delta) % len(self.items)
        self._load_current_image()

    def _max_scroll(self) -> int:
        total_height = len(self.items) * (self.thumb_size + self.thumb_gap) + self.thumb_gap
        return max(0, total_height - self.screen_rect.height)

    def _handle_thumb_click(self, pos: Tuple[int, int]) -> None:
        y = self.thumb_gap - self.scroll_y
        for idx, item in enumerate(self.items):
            rect = pygame.Rect(
                self.strip_rect.left + 12,
                y,
                self.thumb_size,
                self.thumb_size,
            )
            if rect.collidepoint(pos):
                self.current_index = idx
                self._load_current_image()
                break
            y += self.thumb_size + self.thumb_gap

    def _scroll_thumbnails(self, delta: int) -> None:
        self.scroll_y = max(0, min(self._max_scroll(), self.scroll_y + delta))

    def _render(self) -> None:
        self.screen.fill((246, 246, 246))
        pygame.draw.rect(self.screen, (230, 230, 230), self.strip_rect)

        if self.current_image:
            image_rect = self.current_image.get_rect(center=self.main_rect.center)
            self.screen.blit(self.current_image, image_rect)
        else:
            text = self.font.render("No photos found", True, (50, 50, 50))
            self.screen.blit(text, text.get_rect(center=self.main_rect.center))

        y = self.thumb_gap - self.scroll_y
        for idx, item in enumerate(self.items):
            rect = pygame.Rect(
                self.strip_rect.left + 12,
                y,
                self.thumb_size,
                self.thumb_size,
            )
            if rect.bottom >= 0 and rect.top <= self.screen_rect.height:
                if item.thumb:
                    thumb_rect = item.thumb.get_rect(center=rect.center)
                    self.screen.blit(item.thumb, thumb_rect)
                pygame.draw.rect(self.screen, (120, 120, 120), rect, width=2)
                if idx == self.current_index:
                    pygame.draw.rect(self.screen, (200, 60, 60), rect, width=3)
            y += self.thumb_size + self.thumb_gap

        draw_home_button(self.screen, self.home_button.rect)

        if self.show_arrows:
            self.left_arrow.draw(self.screen, self.font)
            self.right_arrow.draw(self.screen, self.font)

        pygame.display.flip()

    def run(self) -> None:
        running = True
        self._render()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.home_button.hit(event.pos):
                        running = False
                    elif self.strip_rect.collidepoint(event.pos):
                        self.strip_drag_last_y = event.pos[1]
                        self._handle_thumb_click(event.pos)
                    elif self.main_rect.collidepoint(event.pos):
                        self.drag_start = event.pos
                        self.drag_delta = (0, 0)
                    if self.show_arrows:
                        if self.left_arrow.hit(event.pos):
                            self._change_index(-1)
                        elif self.right_arrow.hit(event.pos):
                            self._change_index(1)
                elif event.type == pygame.MOUSEMOTION and self.drag_start:
                    self.drag_delta = (event.pos[0] - self.drag_start[0], event.pos[1] - self.drag_start[1])
                elif event.type == pygame.MOUSEMOTION and self.strip_drag_last_y is not None:
                    dy = event.pos[1] - self.strip_drag_last_y
                    self._scroll_thumbnails(-dy)
                    self.strip_drag_last_y = event.pos[1]
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.drag_start:
                        dx, dy = self.drag_delta
                        if abs(dx) > 80 and abs(dx) > abs(dy):
                            if dx < 0:
                                self._change_index(1)
                            else:
                                self._change_index(-1)
                        self.drag_start = None
                        self.drag_delta = (0, 0)
                    self.strip_drag_last_y = None
                elif event.type == pygame.MOUSEWHEEL:
                    if self.strip_rect.collidepoint(pygame.mouse.get_pos()):
                        self._scroll_thumbnails(-event.y * 40)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in {4, 5}:
                    if self.strip_rect.collidepoint(event.pos):
                        self._scroll_thumbnails(-40 if event.button == 4 else 40)

            self._render()
            self.clock.tick(60)

        pygame.quit()


def main() -> None:
    try:
        PhotosApp().run()
    except Exception:
        pygame.quit()


if __name__ == "__main__":
    main()
