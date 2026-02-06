from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from kidbox.config import load_config
from kidbox.paths import ensure_directories, get_data_root
from kidbox.ui.common import Button, create_fullscreen_window, draw_home_button


Color = Tuple[int, int, int]
Point = Tuple[int, int]

FINGERDOWN = getattr(pygame, "FINGERDOWN", None)
FINGERMOTION = getattr(pygame, "FINGERMOTION", None)
FINGERUP = getattr(pygame, "FINGERUP", None)
FINGER_EVENTS = {event for event in (FINGERDOWN, FINGERMOTION, FINGERUP) if event is not None}

_ICON_CACHE: Dict[Tuple[str, Tuple[int, int], bool], pygame.Surface] = {}


def _is_primary_pointer_event(event: pygame.event.Event, *, is_down: bool) -> bool:
    expected_type = pygame.MOUSEBUTTONDOWN if is_down else pygame.MOUSEBUTTONUP
    if event.type == expected_type:
        # Some touch stacks can emit emulated mouse events with button 0.
        button = getattr(event, "button", 1)
        if button in {0, 1}:
            return True
        return bool(getattr(event, "touch", False))
    finger_type = FINGERDOWN if is_down else FINGERUP
    return finger_type is not None and event.type == finger_type


def _fountain_width_for_direction(
    size: int,
    start: Point,
    end: Point,
    *,
    nib_angle_degrees: float = 35.0,
    min_ratio: float = 0.2,
    max_ratio: float = 1.8,
) -> int:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return max(1, int(round(size * ((min_ratio + max_ratio) / 2))))

    direction = math.atan2(dy, dx)
    nib_angle = math.radians(nib_angle_degrees)
    delta = direction - nib_angle
    # Broad-edge nib behavior: narrow parallel to nib axis, wide when crossing it.
    blend = abs(math.sin(delta))
    ratio = min_ratio + (max_ratio - min_ratio) * blend
    return max(1, int(round(size * ratio)))


@dataclass
class Stroke:
    tool: str
    size: int
    color: Color
    points: List[Point]
    fountain_width: float = 0.0


def _save_surface_atomic(surface: pygame.Surface, path: Path) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    pygame.image.save(surface, str(tmp_path))
    os.replace(tmp_path, path)


def _list_archives(paint_dir: Path) -> List[Path]:
    files = list(paint_dir.glob("*.png"))
    files.sort(reverse=True)
    return files


def _load_icon(path: Path, size: Tuple[int, int], *, preserve_aspect: bool = True) -> Optional[pygame.Surface]:
    if not path.exists():
        return None
    key = (str(path), size, preserve_aspect)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        image = pygame.image.load(str(path)).convert_alpha()
    except pygame.error:
        return None
    max_w, max_h = size
    if preserve_aspect:
        width, height = image.get_size()
        scale = min(max_w / width, max_h / height)
        target = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = pygame.transform.smoothscale(image, target)
    else:
        image = pygame.transform.smoothscale(image, (max_w, max_h))
    _ICON_CACHE[key] = image
    return image


def _draw_stamp(
    surface: pygame.Surface,
    kind: str,
    size: int,
    color: Color,
    pos: Point,
    pressure: float = 1.0,
) -> None:
    size = max(2, int(size * pressure))
    pygame.draw.circle(surface, color, pos, size // 2)


def _draw_segment(surface: pygame.Surface, stroke: Stroke, start: Point, end: Point) -> None:
    distance = max(1, pygame.math.Vector2(end).distance_to(start))
    steps = max(1, int(distance / 2))
    for idx in range(steps + 1):
        t = idx / steps
        x = int(start[0] + (end[0] - start[0]) * t)
        y = int(start[1] + (end[1] - start[1]) * t)
        pressure = 1.0
        kind = stroke.tool
        if kind == "eraser":
            kind = "round"
        _draw_stamp(surface, kind, stroke.size, stroke.color, (x, y), pressure=pressure)


def _draw_fountain_segment(
    surface: pygame.Surface,
    color: Color,
    start: Point,
    end: Point,
    start_width: float,
    end_width: float,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    half_start = max(0.5, start_width * 0.5)
    half_end = max(0.5, end_width * 0.5)

    if length < 1e-6:
        radius = max(1, int(round(max(half_start, half_end))))
        pygame.draw.circle(surface, color, start, radius)
        return

    nx = -dy / length
    ny = dx / length
    quad = [
        (start[0] + nx * half_start, start[1] + ny * half_start),
        (start[0] - nx * half_start, start[1] - ny * half_start),
        (end[0] - nx * half_end, end[1] - ny * half_end),
        (end[0] + nx * half_end, end[1] + ny * half_end),
    ]
    points = [(int(round(x)), int(round(y))) for x, y in quad]
    pygame.draw.polygon(surface, color, points)

    # Round joins avoid tiny corner spikes when direction changes quickly.
    pygame.draw.circle(surface, color, (int(round(start[0])), int(round(start[1]))), max(1, int(round(half_start))))
    pygame.draw.circle(surface, color, (int(round(end[0])), int(round(end[1]))), max(1, int(round(half_end))))


def _bucket_fill(surface: pygame.Surface, pos: Point, color: Color) -> None:
    width, height = surface.get_size()
    x, y = pos
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    target = surface.get_at((x, y))[:3]
    if target == color:
        return
    target_mapped = surface.map_rgb(target)
    replacement = surface.map_rgb(color)
    pixels = pygame.PixelArray(surface)
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        if cx < 0 or cy < 0 or cx >= width or cy >= height:
            continue
        if pixels[cx, cy] != target_mapped:
            continue
        pixels[cx, cy] = replacement
        stack.append((cx + 1, cy))
        stack.append((cx - 1, cy))
        stack.append((cx, cy + 1))
        stack.append((cx, cy - 1))
    del pixels


def _load_thumbnail(path: Path, size: Tuple[int, int]) -> Optional[pygame.Surface]:
    try:
        image = pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None
    return pygame.transform.smoothscale(image, size)


def _load_canvas_image(path: Path, size: Tuple[int, int]) -> Optional[pygame.Surface]:
    try:
        image = pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None
    return pygame.transform.smoothscale(image, size)


class PaintApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.data_root = get_data_root(self.config)
        dirs = ensure_directories(self.data_root)
        self.paint_dir = dirs["paint"]

        self.screen, self.screen_rect = create_fullscreen_window()
        self.clock = pygame.time.Clock()

        self.margin = 16
        self.menu_pad = 10
        self.menu_gap = 10
        self.menu_bg = (238, 234, 226)
        self.tool_size = max(44, min(56, int(self.screen_rect.height * 0.06)))
        panel_width = self.tool_size * 2 + self.menu_gap + self.menu_pad * 2
        self.controls_rect = pygame.Rect(
            self.margin,
            self.margin,
            panel_width,
            self.screen_rect.height - 2 * self.margin,
        )
        self.canvas_rect = pygame.Rect(
            self.controls_rect.right + self.margin,
            self.margin,
            self.screen_rect.width - panel_width - 3 * self.margin,
            self.screen_rect.height - 2 * self.margin,
        )

        self.base_surface = pygame.Surface(self.canvas_rect.size)
        self.base_surface.fill((255, 255, 255))
        self.canvas_surface = self.base_surface.copy()

        self.palette = [tuple(color) for color in self.config.get("paint", {}).get("palette", [])]
        self.current_color: Color = self.palette[0] if self.palette else (0, 0, 0)

        self.current_tool = "round"
        self.size_values = self._scaled_size_values()
        self.current_size = self.size_values[0]
        self.undo_stack: List[pygame.Surface] = []
        self.current_stroke: Optional[Stroke] = None

        self.font = pygame.font.SysFont("sans", 18)
        self.last_autosave = time.monotonic()
        self.autosave_interval = int(self.config.get("paint", {}).get("autosave_seconds", 10))

        self.action_buttons: Dict[str, Button] = {}
        self.tool_buttons: Dict[str, Button] = {}
        self.size_buttons: Dict[int, Button] = {}
        self.palette_buttons: List[Button] = []
        self.recall_demo_path = Path(__file__).resolve().parents[3] / "assets" / "recall_demo_1024.png"
        self._build_ui()

        self.recall_open = False
        self.recall_scroll = 0
        self.recall_thumbnails: List[Tuple[pygame.Surface, pygame.Rect, Path]] = []
        self.recall_strip_rect = pygame.Rect(0, 0, 0, 0)
        self.recall_max_scroll = 0
        self.pointer_down = False

    def _scaled_size_values(self) -> List[int]:
        base_sizes = [3, 6, 12]
        scale = min(self.screen_rect.width / 1366, self.screen_rect.height / 768)
        sizes = [max(1, int(round(size * scale))) for size in base_sizes]
        for idx in range(1, len(sizes)):
            if sizes[idx] <= sizes[idx - 1]:
                sizes[idx] = sizes[idx - 1] + 1
        return sizes

    def _build_ui(self) -> None:
        self.action_buttons.clear()
        self.tool_buttons.clear()
        self.size_buttons.clear()
        self.palette_buttons.clear()

        pad = self.menu_pad
        gap = self.menu_gap
        left = self.controls_rect.left + pad
        top = self.controls_rect.top + pad
        inner_w = self.controls_rect.width - pad * 2
        tool_size = min(self.tool_size, int((inner_w - gap) / 2))

        home_size = max(40, int(self.tool_size * 0.85))
        home_rect = pygame.Rect(
            self.screen_rect.right - self.margin - home_size,
            self.margin,
            home_size,
            home_size,
        )
        self.action_buttons["home"] = Button(rect=home_rect, fill=self.menu_bg)

        tool_top = top
        icon_pad = 6
        tool_icons = [
            ("round", Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "brush_round" / "brush_round_256.png"),
            ("fountain", Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "fountain_pen" / "fountain_pen_256.png"),
            ("eraser", Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "eraser" / "eraser_256.png"),
            ("bucket", Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "paint_bucket" / "paint_bucket_256.png"),
        ]
        for idx, (tool, icon_path) in enumerate(tool_icons):
            row = idx // 2
            col = idx % 2
            rect = pygame.Rect(
                left + col * (tool_size + gap),
                tool_top + row * (tool_size + gap),
                tool_size,
                tool_size,
            )
            icon = _load_icon(
                icon_path,
                (max(1, tool_size - icon_pad), max(1, tool_size - icon_pad)),
                preserve_aspect=True,
            )
            self.tool_buttons[tool] = Button(rect=rect, image=icon, fill=self.menu_bg)

        size_height = max(6, tool_size // 2)
        size_gap = max(2, gap // 4)
        size_width = max(1, int(inner_w * 0.6))
        size_left = left + (inner_w - size_width) // 2
        size_top = tool_top + 2 * tool_size + gap
        size_icons = [
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_thin" / "line_thin_256.png",
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_medium" / "line_medium_256.png",
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_fat" / "line_fat_256.png",
        ]
        for idx, (size, icon_path) in enumerate(zip(self.size_values, size_icons)):
            rect = pygame.Rect(
                size_left,
                size_top + idx * (size_height + size_gap),
                size_width,
                size_height,
            )
            icon = _load_icon(
                icon_path,
                (max(1, size_width - icon_pad), max(1, size_height - icon_pad)),
                preserve_aspect=False,
            )
            self.size_buttons[size] = Button(rect=rect, image=icon, fill=self.menu_bg)

        size_bottom = size_top + 3 * size_height + 2 * size_gap

        action_h = self.font.get_height() + 16
        action_gap = gap
        recall_h = inner_w
        bottom_total = recall_h + 2 * action_h + 2 * action_gap
        bottom_top = self.controls_rect.bottom - pad - bottom_total
        bottom_left = left

        recall_rect = pygame.Rect(bottom_left, bottom_top, inner_w, recall_h)
        self.action_buttons["recall"] = Button(rect=recall_rect, label="Recall", fill=self.menu_bg)

        new_rect = pygame.Rect(
            bottom_left,
            recall_rect.bottom + action_gap,
            inner_w,
            action_h,
        )
        self.action_buttons["new"] = Button(rect=new_rect, label="New", fill=(245, 245, 245))

        undo_rect = pygame.Rect(
            bottom_left,
            new_rect.bottom + action_gap,
            inner_w,
            action_h,
        )
        self.action_buttons["undo"] = Button(rect=undo_rect, label="Undo", fill=(245, 245, 245))

        palette_top = size_bottom + gap
        palette_bottom = bottom_top - gap
        if palette_bottom < palette_top:
            palette_bottom = palette_top
        palette_rect = pygame.Rect(left, palette_top, inner_w, palette_bottom - palette_top)

        swatch_gap = 8
        rows = max(1, len(self.palette))
        swatch_height = max(
            14,
            (palette_rect.height - swatch_gap * (rows - 1)) // rows if rows > 0 else 14,
        )
        for idx, color in enumerate(self.palette):
            rect = pygame.Rect(
                palette_rect.left,
                palette_rect.top + idx * (swatch_height + swatch_gap),
                palette_rect.width,
                swatch_height,
            )
            self.palette_buttons.append(Button(rect=rect, fill=color))

        self._update_thumbnail_button()

    def _event_pos(self, event: pygame.event.Event) -> Optional[Point]:
        if hasattr(event, "pos"):
            return event.pos
        if event.type in FINGER_EVENTS:
            return (
                int(event.x * self.screen_rect.width),
                int(event.y * self.screen_rect.height),
            )
        return None

    def _push_undo(self) -> None:
        self.undo_stack.append(self.canvas_surface.copy())
        if len(self.undo_stack) > 10:
            self.undo_stack.pop(0)

    def _undo(self) -> None:
        if self.undo_stack:
            self.canvas_surface = self.undo_stack.pop()

    def _current_draw_color(self) -> Color:
        if self.current_tool == "eraser":
            return (255, 255, 255)
        return self.current_color

    def _handle_pointer_down(self, pos: Point) -> bool:
        if self.action_buttons["home"].hit(pos):
            return True

        if self.canvas_rect.collidepoint(pos):
            local_pos = (pos[0] - self.canvas_rect.left, pos[1] - self.canvas_rect.top)
            if self.current_tool == "bucket":
                self._push_undo()
                _bucket_fill(self.canvas_surface, local_pos, self.current_color)
                return False
            self._push_undo()
            self.current_stroke = Stroke(
                tool=self.current_tool,
                size=self.current_size,
                color=self._current_draw_color(),
                points=[local_pos],
            )
            return False

        for tool, button in self.tool_buttons.items():
            if button.hit(pos):
                self.current_tool = tool
                return False

        for size, button in self.size_buttons.items():
            if button.hit(pos):
                self.current_size = size
                return False

        for idx, button in enumerate(self.palette_buttons):
            if button.hit(pos):
                self.current_color = self.palette[idx]
                return False

        if self.action_buttons["undo"].hit(pos):
            self._undo()
            return False
        if self.action_buttons["new"].hit(pos):
            self._archive_current()
            self._reset_canvas()
            return False
        if self.action_buttons["recall"].hit(pos):
            self._open_recall()
            return False
        return False

    def _handle_pointer_move(self, pos: Point) -> None:
        if not self.current_stroke:
            return
        local_pos = (pos[0] - self.canvas_rect.left, pos[1] - self.canvas_rect.top)
        last_point = self.current_stroke.points[-1]
        if self.current_stroke.tool == "fountain":
            # Densify fountain updates to avoid visible segment artifacts.
            distance = max(1.0, pygame.math.Vector2(local_pos).distance_to(last_point))
            steps = max(1, int(distance / 1.5))
            prev = last_point
            width = self.current_stroke.fountain_width
            for idx in range(1, steps + 1):
                t = idx / steps
                next_point = (
                    int(last_point[0] + (local_pos[0] - last_point[0]) * t),
                    int(last_point[1] + (local_pos[1] - last_point[1]) * t),
                )
                target_width = float(_fountain_width_for_direction(self.current_stroke.size, prev, next_point))
                if width <= 0:
                    width = target_width
                smoothed_width = width + (target_width - width) * 0.35
                _draw_fountain_segment(
                    self.canvas_surface,
                    self.current_stroke.color,
                    prev,
                    next_point,
                    width,
                    smoothed_width,
                )
                width = smoothed_width
                self.current_stroke.points.append(next_point)
                prev = next_point
            self.current_stroke.fountain_width = width
            return
        self.current_stroke.points.append(local_pos)
        _draw_segment(self.canvas_surface, self.current_stroke, last_point, local_pos)

    def _handle_pointer_up(self) -> None:
        self.current_stroke = None

    def _update_thumbnail_button(self) -> None:
        archives = _list_archives(self.paint_dir)
        size = self.action_buttons["recall"].rect.size
        icon_size = (max(1, size[0] - 6), max(1, size[1] - 6))
        icon = None
        for candidate in archives:
            if not candidate.exists():
                continue
            icon = _load_icon(candidate, icon_size)
            if icon is not None:
                break
        if icon is None and self.recall_demo_path.exists():
            icon = _load_icon(self.recall_demo_path, icon_size)
        self.action_buttons["recall"].image = icon

    def _autosave_latest(self) -> None:
        latest_path = self.paint_dir / "latest.png"
        _save_surface_atomic(self.canvas_surface, latest_path)

    def _archive_current(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_path = self.paint_dir / f"{timestamp}.png"
        _save_surface_atomic(self.canvas_surface, archive_path)
        self._update_thumbnail_button()

    def _reset_canvas(self) -> None:
        self.base_surface.fill((255, 255, 255))
        self.canvas_surface = self.base_surface.copy()
        self.undo_stack = []

    def _open_recall(self) -> None:
        archives = _list_archives(self.paint_dir)
        if not archives and self.recall_demo_path.exists():
            archives = [self.recall_demo_path]
        thumb_size = 140
        padding = 16
        strip_height = thumb_size + padding * 2
        self.recall_strip_rect = pygame.Rect(0, (self.screen_rect.height - strip_height) // 2, self.screen_rect.width, strip_height)
        self.recall_thumbnails = []
        x = padding
        for path in archives:
            image = _load_thumbnail(path, (thumb_size, thumb_size))
            if image is None:
                continue
            rect = pygame.Rect(x, self.recall_strip_rect.top + padding, thumb_size, thumb_size)
            self.recall_thumbnails.append((image, rect, path))
            x += thumb_size + padding
        if not self.recall_thumbnails and self.recall_demo_path.exists():
            image = _load_thumbnail(self.recall_demo_path, (thumb_size, thumb_size))
            if image is not None:
                rect = pygame.Rect(x, self.recall_strip_rect.top + padding, thumb_size, thumb_size)
                self.recall_thumbnails.append((image, rect, self.recall_demo_path))
                x += thumb_size + padding
        if not self.recall_thumbnails:
            return
        self.recall_scroll = 0
        self.recall_max_scroll = max(0, x - self.screen_rect.width)
        self.recall_open = True

    def _handle_recall_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.recall_open = False
            return
        if _is_primary_pointer_event(event, is_down=True):
            pos = self._event_pos(event)
            if pos is None:
                return
            self.pointer_down = True
            if not self.recall_strip_rect.collidepoint(pos):
                self.recall_open = False
                return
            for image, rect, path in self.recall_thumbnails:
                moved_rect = rect.move(-self.recall_scroll, 0)
                if moved_rect.collidepoint(pos):
                    loaded = _load_canvas_image(path, self.canvas_rect.size)
                    if loaded is None:
                        continue
                    self.canvas_surface = loaded.copy()
                    self.undo_stack = []
                    self.recall_open = False
                    return
        if _is_primary_pointer_event(event, is_down=False):
            self.pointer_down = False
        if event.type == pygame.MOUSEWHEEL:
            delta = event.x if event.x != 0 else -event.y
            new_scroll = self.recall_scroll - delta * 40
            self.recall_scroll = max(0, min(self.recall_max_scroll, new_scroll))
        if event.type == pygame.MOUSEMOTION and (self.pointer_down or event.buttons[0]):
            new_scroll = self.recall_scroll - event.rel[0]
            self.recall_scroll = max(0, min(self.recall_max_scroll, new_scroll))
        if FINGERMOTION is not None and event.type == FINGERMOTION and self.pointer_down:
            new_scroll = self.recall_scroll - int(event.dx * self.screen_rect.width)
            self.recall_scroll = max(0, min(self.recall_max_scroll, new_scroll))

    def _draw_recall_overlay(self) -> None:
        overlay = pygame.Surface(self.screen_rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (230, 230, 230), self.recall_strip_rect)
        for image, rect, _ in self.recall_thumbnails:
            moved_rect = rect.move(-self.recall_scroll, 0)
            if moved_rect.right < 0 or moved_rect.left > self.screen_rect.width:
                continue
            self.screen.blit(image, moved_rect)

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if self.recall_open:
                    self._handle_recall_event(event)
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif _is_primary_pointer_event(event, is_down=True):
                    pos = self._event_pos(event)
                    if pos is None:
                        continue
                    self.pointer_down = True
                    if self._handle_pointer_down(pos):
                        running = False
                elif event.type == pygame.MOUSEMOTION or (FINGERMOTION is not None and event.type == FINGERMOTION):
                    if event.type == pygame.MOUSEMOTION:
                        if not (self.pointer_down or event.buttons[0]):
                            continue
                    elif not self.pointer_down:
                        continue
                    pos = self._event_pos(event)
                    if pos is None:
                        continue
                    self._handle_pointer_move(pos)
                elif _is_primary_pointer_event(event, is_down=False):
                    self.pointer_down = False
                    self._handle_pointer_up()

            now = time.monotonic()
            if now - self.last_autosave >= self.autosave_interval:
                self._autosave_latest()
                self.last_autosave = now

            self.screen.fill((252, 248, 240))
            pygame.draw.rect(self.screen, self.menu_bg, self.controls_rect)
            self.screen.blit(self.canvas_surface, self.canvas_rect.topleft)
            pygame.draw.rect(self.screen, (200, 200, 200), self.canvas_rect, width=2)

            for tool, button in self.tool_buttons.items():
                button.draw(self.screen)
                if tool == self.current_tool:
                    pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3, border_radius=12)

            for size, button in self.size_buttons.items():
                button.draw(self.screen)
                if size == self.current_size:
                    pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3, border_radius=12)

            for idx, button in enumerate(self.palette_buttons):
                button.draw(self.screen)
                if self.palette[idx] == self.current_color:
                    pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3)

            for key, button in self.action_buttons.items():
                if key == "home":
                    draw_home_button(self.screen, button.rect)
                else:
                    if key in {"new", "undo"}:
                        button.draw(self.screen, self.font)
                    elif key == "recall" and button.image is None:
                        button.draw(self.screen, self.font)
                    else:
                        button.draw(self.screen)

            if self.recall_open:
                self._draw_recall_overlay()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


def main() -> None:
    try:
        PaintApp().run()
    except Exception:
        pygame.quit()


if __name__ == "__main__":
    main()
