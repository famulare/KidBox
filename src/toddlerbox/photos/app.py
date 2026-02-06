from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional, Tuple

import pygame
try:
    from PIL import Image
except Exception:
    Image = None

FINGERMOTION = getattr(pygame, "FINGERMOTION", None)

from toddlerbox.config import load_config
from toddlerbox.paths import ensure_directories, get_data_root
from toddlerbox.ui.common import (
    Button,
    create_fullscreen_window,
    draw_home_button,
    is_primary_pointer_event,
    pointer_event_pos,
)


@dataclass
class PhotoItem:
    path: Path
    thumb: Optional[pygame.Surface] = None


_EXIF_DATE_TAGS = (36867, 36868, 306)


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


def _parse_exif_datetime(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        # EXIF uses "YYYY:MM:DD HH:MM:SS"
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _photo_taken_at(path: Path) -> Optional[datetime]:
    if Image is None:
        return None
    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except Exception:
        return None

    if not exif:
        return None
    for tag in _EXIF_DATE_TAGS:
        taken = _parse_exif_datetime(exif.get(tag))
        if taken is not None:
            return taken
    return None


def _list_photos(library_dir: Path, exif_cache: dict[str, Optional[float]]) -> Tuple[List[Path], bool]:
    dirty = False

    def sort_key(path: Path) -> Tuple[int, float, str]:
        nonlocal dirty
        rel = str(path.relative_to(library_dir))
        if rel in exif_cache:
            cached = exif_cache[rel]
            if cached is not None:
                return (0, -cached, path.name.lower())
        else:
            taken = _photo_taken_at(path)
            if taken is not None:
                exif_cache[rel] = taken.timestamp()
                dirty = True
                return (0, -exif_cache[rel], path.name.lower())
            exif_cache[rel] = None
            dirty = True
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (1, -mtime, path.name.lower())

    return (
        sorted((path for path in library_dir.iterdir() if _is_image(path)), key=sort_key),
        dirty,
    )


def _load_exif_cache(path: Path) -> dict[str, Optional[float]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {str(key): (val if isinstance(val, (int, float)) or val is None else None) for key, val in data.items()}
    except Exception:
        pass
    return {}


def _save_exif_cache(path: Path, data: dict[str, Optional[float]]) -> None:
    try:
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle)
        tmp_path.replace(path)
    except Exception:
        pass


class PhotosApp:
    def __init__(
        self,
        *,
        screen: Optional[pygame.Surface] = None,
        screen_rect: Optional[pygame.Rect] = None,
        clock: Optional[pygame.time.Clock] = None,
    ) -> None:
        self.config = load_config()
        self.data_root = get_data_root(self.config)
        dirs = ensure_directories(self.data_root)
        self.photos_dir = dirs["photos"]
        self.library_dir = self.photos_dir / "library"
        self.thumb_dir = self.photos_dir / "thumbs"
        self.exif_cache_path = self.thumb_dir / "exif_cache.json"

        if screen is None:
            self.screen, self.screen_rect = create_fullscreen_window()
        else:
            self.screen = screen
            self.screen_rect = screen_rect or screen.get_rect()
        self.clock = clock or pygame.time.Clock()

        base_strip_width = max(160, int(self.screen_rect.width * 0.25))
        self.strip_width = max(112, int(base_strip_width * 0.7))
        self.strip_rect = pygame.Rect(
            0,
            0,
            self.strip_width,
            self.screen_rect.height,
        )
        self.main_rect = pygame.Rect(self.strip_width, 0, self.screen_rect.width - self.strip_width, self.screen_rect.height)

        self.thumb_padding_x = 12
        self.thumb_gap = 12
        self.thumb_width = max(1, self.strip_rect.width - (self.thumb_padding_x * 2))
        self.thumb_size = self.thumb_width
        self.scroll_y = 0

        self.exif_cache = _load_exif_cache(self.exif_cache_path)
        photo_paths, cache_dirty = _list_photos(self.library_dir, self.exif_cache)
        self.items = [PhotoItem(path) for path in photo_paths]
        self.current_index = 0
        self.current_image: Optional[pygame.Surface] = None
        self.initial_thumb_count = int(self.config.get("photos", {}).get("initial_thumbs", 10))
        self.thumb_load_batch = int(self.config.get("photos", {}).get("thumb_batch", 2))
        self.thumb_idle_ms = int(self.config.get("photos", {}).get("thumb_idle_ms", 400))
        self.thumb_scroll_idle_ms = int(self.config.get("photos", {}).get("thumb_scroll_idle_ms", 700))
        self.thumb_time_budget_ms = int(self.config.get("photos", {}).get("thumb_time_budget_ms", 3))
        self._init_thumb_queue()
        self._load_initial_thumbnails()
        if cache_dirty:
            _save_exif_cache(self.exif_cache_path, self.exif_cache)
        self._load_current_image()

        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_delta: Tuple[int, int] = (0, 0)
        self.strip_drag_last_y: Optional[int] = None
        self.strip_pressed_index: Optional[int] = None
        self.strip_drag_distance = 0
        self.show_arrows = bool(self.config.get("photos", {}).get("show_arrows", False))
        self.font = pygame.font.SysFont("sans", 18)

        self.home_button = Button(rect=pygame.Rect(self.screen_rect.width - 90, 20, 70, 50), fill=(240, 240, 240))
        self.left_arrow = Button(rect=pygame.Rect(self.main_rect.left + 20, self.screen_rect.centery - 30, 50, 60), fill=(245, 245, 245))
        self.right_arrow = Button(rect=pygame.Rect(self.main_rect.right - 70, self.screen_rect.centery - 30, 50, 60), fill=(245, 245, 245))

    def _init_thumb_queue(self) -> None:
        self._pending_order = list(range(len(self.items)))
        self._pending_set = set(self._pending_order)
        self._pending_cursor = 0

    def _load_initial_thumbnails(self) -> None:
        initial_count = max(0, min(self.initial_thumb_count, len(self._pending_order)))
        for idx in range(initial_count):
            self._load_thumbnail_for_index(idx)
            self._pending_set.discard(idx)
        self._pending_cursor = initial_count

    def _visible_indices(self) -> List[int]:
        indices: List[int] = []
        y = self.thumb_gap - self.scroll_y
        for idx, _item in enumerate(self.items):
            rect = pygame.Rect(
                self.strip_rect.left + self.thumb_padding_x,
                y,
                self.thumb_width,
                self.thumb_size,
            )
            if rect.bottom >= 0 and rect.top <= self.screen_rect.height:
                indices.append(idx)
            y += self.thumb_size + self.thumb_gap
        return indices

    def _next_pending_index(self, prefer_indices: Optional[List[int]]) -> Optional[int]:
        if prefer_indices:
            for idx in prefer_indices:
                if idx in self._pending_set:
                    return idx
        while self._pending_cursor < len(self._pending_order):
            idx = self._pending_order[self._pending_cursor]
            self._pending_cursor += 1
            if idx in self._pending_set:
                return idx
        return None

    def _load_next_thumbnail(self, prefer_indices: Optional[List[int]] = None) -> None:
        if not self._pending_set:
            return
        idx = self._next_pending_index(prefer_indices)
        if idx is None:
            return
        self._load_thumbnail_for_index(idx)
        self._pending_set.discard(idx)

    def _load_thumbnail_for_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.items):
            return
        item = self.items[idx]
        if item.thumb is not None:
            return
        thumb_path = self.thumb_dir / _thumb_name(item.path)
        try:
            source_mtime = item.path.stat().st_mtime
        except OSError:
            return
        if thumb_path.exists():
            try:
                if thumb_path.stat().st_mtime >= source_mtime:
                    loaded_thumb = pygame.image.load(str(thumb_path)).convert_alpha()
                    item.thumb = self._fit_thumb_surface(loaded_thumb)
                    return
            except Exception:
                pass
        try:
            image = pygame.image.load(str(item.path)).convert_alpha()
            thumb = self._fit_thumb_surface(image)
            pygame.image.save(thumb, str(thumb_path))
            item.thumb = thumb
        except Exception:
            item.thumb = None

    def _cleanup_caches(self) -> None:
        try:
            library_set = {str(path.relative_to(self.library_dir)) for path in self.library_dir.iterdir() if _is_image(path)}
        except Exception:
            library_set = set()

        cache_dirty = False
        for rel in list(self.exif_cache.keys()):
            if rel not in library_set:
                self.exif_cache.pop(rel, None)
                cache_dirty = True
        if cache_dirty:
            _save_exif_cache(self.exif_cache_path, self.exif_cache)

        try:
            for thumb_path in self.thumb_dir.iterdir():
                if thumb_path.name == self.exif_cache_path.name or thumb_path.suffix.lower() != ".png":
                    continue
                name = thumb_path.stem
                if "_" not in name:
                    continue
                stem, suffix = name.rsplit("_", 1)
                source_path = self.library_dir / f"{stem}.{suffix}"
                if not source_path.exists():
                    try:
                        thumb_path.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def _fit_thumb_surface(self, surface: pygame.Surface) -> pygame.Surface:
        if surface.get_width() <= self.thumb_width and surface.get_height() <= self.thumb_size:
            return surface
        return _scale_to_fit(surface, (self.thumb_width, self.thumb_size))

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

    def _thumb_index_at_pos(self, pos: Tuple[int, int]) -> Optional[int]:
        y = self.thumb_gap - self.scroll_y
        for idx, _item in enumerate(self.items):
            rect = pygame.Rect(
                self.strip_rect.left + self.thumb_padding_x,
                y,
                self.thumb_width,
                self.thumb_size,
            )
            if rect.collidepoint(pos):
                return idx
            y += self.thumb_size + self.thumb_gap
        return None

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
                self.strip_rect.left + self.thumb_padding_x,
                y,
                self.thumb_width,
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

    def run(self, *, quit_on_exit: bool = True) -> None:
        running = True
        self._render()
        self._cleanup_caches()
        last_input_ms = pygame.time.get_ticks()
        last_scroll_ms = last_input_ms
        while running:
            for event in pygame.event.get():
                if event.type in {
                    pygame.MOUSEMOTION,
                    pygame.MOUSEBUTTONDOWN,
                    pygame.MOUSEBUTTONUP,
                    pygame.MOUSEWHEEL,
                    pygame.KEYDOWN,
                    getattr(pygame, "FINGERDOWN", None),
                    getattr(pygame, "FINGERUP", None),
                    FINGERMOTION,
                }:
                    last_input_ms = pygame.time.get_ticks()
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif is_primary_pointer_event(event, is_down=True):
                    pos = pointer_event_pos(event, self.screen_rect)
                    if pos is None:
                        continue
                    if self.home_button.hit(pos):
                        running = False
                    elif self.strip_rect.collidepoint(pos):
                        self.strip_drag_last_y = pos[1]
                        self.strip_pressed_index = self._thumb_index_at_pos(pos)
                        self.strip_drag_distance = 0
                    elif self.main_rect.collidepoint(pos):
                        self.drag_start = pos
                        self.drag_delta = (0, 0)
                    if self.show_arrows:
                        if self.left_arrow.hit(pos):
                            self._change_index(-1)
                        elif self.right_arrow.hit(pos):
                            self._change_index(1)
                elif event.type == pygame.MOUSEMOTION or (FINGERMOTION is not None and event.type == FINGERMOTION):
                    pos = pointer_event_pos(event, self.screen_rect)
                    if pos is None:
                        continue
                    if self.drag_start:
                        self.drag_delta = (pos[0] - self.drag_start[0], pos[1] - self.drag_start[1])
                    if self.strip_drag_last_y is not None:
                        dy = pos[1] - self.strip_drag_last_y
                        self._scroll_thumbnails(-dy)
                        last_scroll_ms = pygame.time.get_ticks()
                        self.strip_drag_distance += abs(dy)
                        self.strip_drag_last_y = pos[1]
                elif is_primary_pointer_event(event, is_down=False):
                    pos = pointer_event_pos(event, self.screen_rect)
                    if pos is None:
                        continue
                    if self.drag_start:
                        dx, dy = self.drag_delta
                        if abs(dx) > 80 and abs(dx) > abs(dy):
                            if dx < 0:
                                self._change_index(1)
                            else:
                                self._change_index(-1)
                        self.drag_start = None
                        self.drag_delta = (0, 0)
                    if (
                        self.strip_pressed_index is not None
                        and self.strip_drag_distance < 10
                        and self._thumb_index_at_pos(pos) == self.strip_pressed_index
                    ):
                        self.current_index = self.strip_pressed_index
                        self._load_current_image()
                    self.strip_drag_last_y = None
                    self.strip_pressed_index = None
                    self.strip_drag_distance = 0
                elif event.type == pygame.MOUSEWHEEL:
                    if self.strip_rect.collidepoint(pygame.mouse.get_pos()):
                        self._scroll_thumbnails(-event.y * 40)
                        last_scroll_ms = pygame.time.get_ticks()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button in {4, 5}:
                    if self.strip_rect.collidepoint(event.pos):
                        self._scroll_thumbnails(-40 if event.button == 4 else 40)
                        last_scroll_ms = pygame.time.get_ticks()

            self._render()
            now_ms = pygame.time.get_ticks()
            active = (
                now_ms - last_input_ms < self.thumb_idle_ms
                or now_ms - last_scroll_ms < self.thumb_scroll_idle_ms
            )
            budget_end = now_ms + self.thumb_time_budget_ms
            batch = 1 if active else self.thumb_load_batch
            visible_indices = None if active else self._visible_indices()
            for _ in range(batch):
                self._load_next_thumbnail(visible_indices)
                if pygame.time.get_ticks() >= budget_end:
                    break
            self.clock.tick(60)

        if quit_on_exit:
            pygame.quit()


def main() -> None:
    try:
        PhotosApp().run(quit_on_exit=True)
    except Exception:
        pygame.quit()


def run_embedded(screen: pygame.Surface, screen_rect: pygame.Rect, clock: pygame.time.Clock) -> None:
    PhotosApp(screen=screen, screen_rect=screen_rect, clock=clock).run(quit_on_exit=False)


class PhotosPrewarmer:
    def __init__(self, screen_rect: pygame.Rect) -> None:
        config = load_config()
        data_root = get_data_root(config)
        dirs = ensure_directories(data_root)
        self.library_dir = dirs["photos"] / "library"
        self.thumb_dir = dirs["photos"] / "thumbs"
        self.exif_cache_path = self.thumb_dir / "exif_cache.json"
        self.exif_cache = _load_exif_cache(self.exif_cache_path)

        base_strip_width = max(160, int(screen_rect.width * 0.25))
        strip_width = max(112, int(base_strip_width * 0.7))
        thumb_padding_x = 12
        self.thumb_width = max(1, strip_width - (thumb_padding_x * 2))
        self.thumb_size = self.thumb_width

        photo_paths, cache_dirty = _list_photos(self.library_dir, self.exif_cache)
        self.items = [PhotoItem(path) for path in photo_paths]
        if cache_dirty:
            _save_exif_cache(self.exif_cache_path, self.exif_cache)

        self.pending = list(range(len(self.items)))
        self.pending_set = set(self.pending)
        self.pending_cursor = 0

    def step(self, batch: int) -> None:
        for _ in range(max(0, batch)):
            idx = self._next_pending_index()
            if idx is None:
                return
            self._load_thumbnail_for_index(idx)
            self.pending_set.discard(idx)

    def _next_pending_index(self) -> Optional[int]:
        while self.pending_cursor < len(self.pending):
            idx = self.pending[self.pending_cursor]
            self.pending_cursor += 1
            if idx in self.pending_set:
                return idx
        return None

    def _fit_thumb_surface(self, surface: pygame.Surface) -> pygame.Surface:
        if surface.get_width() <= self.thumb_width and surface.get_height() <= self.thumb_size:
            return surface
        return _scale_to_fit(surface, (self.thumb_width, self.thumb_size))

    def _load_thumbnail_for_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.items):
            return
        item = self.items[idx]
        thumb_path = self.thumb_dir / _thumb_name(item.path)
        try:
            source_mtime = item.path.stat().st_mtime
        except OSError:
            return
        if thumb_path.exists():
            try:
                if thumb_path.stat().st_mtime >= source_mtime:
                    return
            except Exception:
                pass
        try:
            image = pygame.image.load(str(item.path)).convert_alpha()
            thumb = self._fit_thumb_surface(image)
            pygame.image.save(thumb, str(thumb_path))
        except Exception:
            return


if __name__ == "__main__":
    main()
