from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from toddlerbox.config import load_config
from toddlerbox.paths import ensure_directories, get_data_root
from toddlerbox.ui.common import (
    Button,
    create_fullscreen_window,
    draw_home_button,
    is_primary_pointer_event,
    pointer_event_pos,
)


Color = Tuple[int, int, int]
Point = Tuple[int, int]

FINGERMOTION = getattr(pygame, "FINGERMOTION", None)

# --- Tuning constants ---
DRAG_THRESHOLD = 10
UNDO_MAX_DEPTH = 10
FOUNTAIN_SMOOTHING = 0.35
FOUNTAIN_DENSITY = 1.5
SCROLL_STEP = 40
MAX_ARCHIVES = 100

_ICON_CACHE: Dict[Tuple[str, Tuple[int, int], bool], pygame.Surface] = {}


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


@dataclass
class RecallItem:
    thumb: pygame.Surface
    source: Optional[Path] = None


def _save_surface_atomic(surface: pygame.Surface, path: Path) -> None:
    # Keep a .png suffix so pygame writes a PNG-encoded file.
    tmp_path = path.with_name(f".{path.stem}.tmp{path.suffix}")
    pygame.image.save(surface, str(tmp_path))
    os.replace(tmp_path, path)


def _list_archives(paint_dir: Path) -> List[Path]:
    files = list(paint_dir.glob("*.png"))
    files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return files


def _rollover_latest_snapshot(paint_dir: Path, now: Optional[datetime] = None) -> Optional[Path]:
    latest_path = paint_dir / "latest.png"
    if not latest_path.exists():
        return None
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    archive_path = paint_dir / f"{stamp}.png"
    counter = 1
    while archive_path.exists():
        archive_path = paint_dir / f"{stamp}_{counter}.png"
        counter += 1
    try:
        os.replace(latest_path, archive_path)
    except OSError:
        return None
    return archive_path


def _coerce_archive_limit(value: object, default: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, limit)


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
    visited: set = set()
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        if cx < 0 or cy < 0 or cx >= width or cy >= height:
            continue
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
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
        self.paint_dir = dirs["paint"]
        _rollover_latest_snapshot(self.paint_dir)

        if screen is None:
            self.screen, self.screen_rect = create_fullscreen_window()
        else:
            self.screen = screen
            self.screen_rect = screen_rect or screen.get_rect()
        self.clock = clock or pygame.time.Clock()

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

        self.current_tool = "fountain"
        self.size_values = self._scaled_size_values()
        self.current_size = self.size_values[1] if len(self.size_values) > 1 else self.size_values[0]
        self.undo_stack: List[pygame.Surface] = []
        self.redo_stack: List[pygame.Surface] = []
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
        self.recall_items: List[RecallItem] = []
        self.recall_strip_rect = pygame.Rect(0, 0, 0, 0)
        self.recall_scroll_y = 0
        self.recall_max_scroll = 0
        self.recall_thumb_padding_x = 12
        self.recall_thumb_gap = 12
        self.recall_thumb_size = 0
        self.recall_strip_drag_last_y: Optional[int] = None
        self.recall_pressed_index: Optional[int] = None
        self.recall_drag_distance = 0
        self.pointer_down = False
        self._recall_overlay = pygame.Surface(self.screen_rect.size, pygame.SRCALPHA)
        self._recall_overlay.fill((0, 0, 0, 140))

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

        size_gap = max(2, gap // 4)
        size_width = max(1, (inner_w - 2 * size_gap) // 3)
        size_height = max(24, int(tool_size * 1.1))
        size_left = left
        size_top = tool_top + 2 * tool_size + gap
        size_icons = [
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_thin" / "line_thin_256.png",
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_medium" / "line_medium_256.png",
            Path(__file__).resolve().parents[3] / "assets" / "icons" / "paint" / "line_fat" / "line_fat_256.png",
        ]
        for idx, (size, icon_path) in enumerate(zip(self.size_values, size_icons)):
            rect = pygame.Rect(
                size_left + idx * (size_width + size_gap),
                size_top,
                size_width,
                size_height,
            )
            icon = _load_icon(
                icon_path,
                (max(1, size_height - icon_pad), max(1, size_width - icon_pad)),
                preserve_aspect=False,
            )
            if icon is not None:
                icon = pygame.transform.rotate(icon, 90)
            self.size_buttons[size] = Button(rect=rect, image=icon, fill=self.menu_bg)

        size_bottom = size_top + size_height

        action_h = self.font.get_height() + 16
        action_gap = gap
        recall_new_gap = 2
        recall_h = min(
            inner_w,
            max(1, int(inner_w * (self.canvas_rect.height / self.canvas_rect.width))),
        )
        bottom_total = recall_h + 2 * action_h + recall_new_gap + action_gap
        bottom_top = self.controls_rect.bottom - pad - bottom_total
        bottom_left = left

        recall_rect = pygame.Rect(bottom_left, bottom_top, inner_w, recall_h)
        self.action_buttons["recall"] = Button(rect=recall_rect, label="Recall", fill=self.menu_bg)

        new_rect = pygame.Rect(
            bottom_left,
            recall_rect.bottom + recall_new_gap,
            inner_w,
            action_h,
        )
        self.action_buttons["new"] = Button(rect=new_rect, label="New", fill=(245, 245, 245))

        half_w = max(1, (inner_w - action_gap) // 2)
        undo_rect = pygame.Rect(
            bottom_left,
            new_rect.bottom + action_gap,
            half_w,
            action_h,
        )
        self.action_buttons["undo"] = Button(rect=undo_rect, label="Undo", fill=(245, 245, 245))

        redo_rect = pygame.Rect(
            bottom_left + half_w + action_gap,
            new_rect.bottom + action_gap,
            half_w,
            action_h,
        )
        self.action_buttons["redo"] = Button(rect=redo_rect, label="Redo", fill=(245, 245, 245))

        palette_gap = max(4, gap // 2)
        palette_top = size_bottom + palette_gap + 4
        palette_bottom = bottom_top - 4
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
        return pointer_event_pos(event, self.screen_rect)

    def _push_undo(self) -> None:
        self.undo_stack.append(self.canvas_surface.copy())
        if len(self.undo_stack) > UNDO_MAX_DEPTH:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append(self.canvas_surface.copy())
            self.canvas_surface = self.undo_stack.pop()

    def _redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append(self.canvas_surface.copy())
            self.canvas_surface = self.redo_stack.pop()

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
        if self.action_buttons["redo"].hit(pos):
            self._redo()
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
            steps = max(1, int(distance / FOUNTAIN_DENSITY))
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
                smoothed_width = width + (target_width - width) * FOUNTAIN_SMOOTHING
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
        counter = 1
        while archive_path.exists():
            archive_path = self.paint_dir / f"{timestamp}_{counter}.png"
            counter += 1
        _save_surface_atomic(self.canvas_surface, archive_path)
        self._enforce_archive_limit()
        self._update_thumbnail_button()

    def _enforce_archive_limit(self) -> None:
        max_archives = _coerce_archive_limit(
            self.config.get("paint", {}).get("max_archives", MAX_ARCHIVES),
            MAX_ARCHIVES,
        )
        archives = _list_archives(self.paint_dir)
        # Exclude latest.png from the count
        archives = [p for p in archives if p.name != "latest.png"]
        while len(archives) > max_archives and archives:
            oldest = archives.pop()  # list is sorted newest-first
            try:
                oldest.unlink()
            except OSError:
                break

    def _reset_canvas(self) -> None:
        self.base_surface.fill((255, 255, 255))
        self.canvas_surface = self.base_surface.copy()
        self.undo_stack = []
        self.redo_stack = []

    def _open_recall(self) -> None:
        # Persist current canvas before showing recall so latest work appears immediately.
        self._autosave_latest()
        self._update_thumbnail_button()
        self.recall_strip_rect = self.controls_rect.copy()
        self.recall_thumb_size = max(1, self.recall_strip_rect.width - (self.recall_thumb_padding_x * 2))
        self.recall_items = [
            RecallItem(thumb=pygame.transform.smoothscale(self.canvas_surface, (self.recall_thumb_size, self.recall_thumb_size)))
        ]
        archives = [path for path in _list_archives(self.paint_dir) if path.name != "latest.png"]
        if not archives and self.recall_demo_path.exists():
            archives = [self.recall_demo_path]
        for path in archives:
            image = _load_thumbnail(path, (self.recall_thumb_size, self.recall_thumb_size))
            if image is None:
                continue
            self.recall_items.append(RecallItem(thumb=image, source=path))
        self.recall_scroll_y = 0
        self.recall_strip_drag_last_y = None
        self.recall_pressed_index = None
        self.recall_drag_distance = 0
        self.recall_max_scroll = self._recall_max_scroll()
        self.recall_open = True

    def _recall_max_scroll(self) -> int:
        total_height = len(self.recall_items) * (self.recall_thumb_size + self.recall_thumb_gap) + self.recall_thumb_gap
        return max(0, total_height - self.recall_strip_rect.height)

    def _scroll_recall(self, delta: int) -> None:
        self.recall_scroll_y = max(0, min(self.recall_max_scroll, self.recall_scroll_y + delta))

    def _recall_item_rect(self, index: int) -> pygame.Rect:
        y = self.recall_thumb_gap - self.recall_scroll_y + index * (self.recall_thumb_size + self.recall_thumb_gap)
        return pygame.Rect(
            self.recall_strip_rect.left + self.recall_thumb_padding_x,
            self.recall_strip_rect.top + y,
            self.recall_thumb_size,
            self.recall_thumb_size,
        )

    def _handle_recall_selection(self, item: RecallItem) -> None:
        if item.source is None:
            self.recall_open = False
            return
        loaded = _load_canvas_image(item.source, self.canvas_rect.size)
        if loaded is None:
            return
        self.canvas_surface = loaded.copy()
        self.undo_stack = []
        self.redo_stack = []
        # Always promote selected archive into latest working copy.
        self._autosave_latest()
        self.last_autosave = time.monotonic()
        self._update_thumbnail_button()
        self.recall_open = False

    def _recall_index_at_pos(self, pos: Point) -> Optional[int]:
        for idx, _ in enumerate(self.recall_items):
            if self._recall_item_rect(idx).collidepoint(pos):
                return idx
        return None

    def _handle_recall_event(self, event: pygame.event.Event) -> None:
        if is_primary_pointer_event(event, is_down=True):
            if self.pointer_down:
                # Ignore duplicate emulated pointer-down events from touch stacks.
                return
            pos = self._event_pos(event)
            if pos is None:
                return
            self.pointer_down = True
            if not self.recall_strip_rect.collidepoint(pos):
                self.recall_open = False
                self.pointer_down = False
                self.recall_strip_drag_last_y = None
                self.recall_pressed_index = None
                self.recall_drag_distance = 0
                return
            self.recall_strip_drag_last_y = pos[1]
            self.recall_pressed_index = self._recall_index_at_pos(pos)
            self.recall_drag_distance = 0
        if is_primary_pointer_event(event, is_down=False):
            if not self.pointer_down:
                # Ignore duplicate emulated pointer-up events.
                return
            self.pointer_down = False
            pos = self._event_pos(event)
            if (
                pos is not None
                and self.recall_drag_distance < DRAG_THRESHOLD
                and self.recall_pressed_index is not None
                and self._recall_index_at_pos(pos) == self.recall_pressed_index
            ):
                self._handle_recall_selection(self.recall_items[self.recall_pressed_index])
            self.recall_strip_drag_last_y = None
            self.recall_pressed_index = None
            self.recall_drag_distance = 0
        if event.type == pygame.MOUSEWHEEL:
            if self.recall_strip_rect.collidepoint(pygame.mouse.get_pos()):
                self._scroll_recall(-event.y * SCROLL_STEP)
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", None) in {4, 5}:
            pos = self._event_pos(event)
            if pos and self.recall_strip_rect.collidepoint(pos):
                self._scroll_recall(-SCROLL_STEP if event.button == 4 else SCROLL_STEP)
        if event.type == pygame.MOUSEMOTION and self.recall_strip_drag_last_y is not None:
            dy = event.pos[1] - self.recall_strip_drag_last_y
            self._scroll_recall(-dy)
            self.recall_drag_distance += abs(dy)
            self.recall_strip_drag_last_y = event.pos[1]
        if FINGERMOTION is not None and event.type == FINGERMOTION and self.pointer_down:
            current_y = int(event.y * self.screen_rect.height)
            if self.recall_strip_drag_last_y is None:
                self.recall_strip_drag_last_y = current_y
            dy = current_y - self.recall_strip_drag_last_y
            self._scroll_recall(-dy)
            self.recall_drag_distance += abs(dy)
            self.recall_strip_drag_last_y = current_y

    def _draw_recall_overlay(self) -> None:
        self.screen.blit(self._recall_overlay, (0, 0))
        pygame.draw.rect(self.screen, (230, 230, 230), self.recall_strip_rect)
        for idx, item in enumerate(self.recall_items):
            rect = self._recall_item_rect(idx)
            if rect.bottom < self.recall_strip_rect.top or rect.top > self.recall_strip_rect.bottom:
                continue
            self.screen.blit(item.thumb, rect)
            border_color = (200, 60, 60) if idx == 0 else (120, 120, 120)
            pygame.draw.rect(self.screen, border_color, rect, width=3 if idx == 0 else 2)

    def _render(self) -> None:
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
            color = self.palette[idx]
            if color == self.current_color:
                pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3)
                inner = button.rect.inflate(-4, -4)
                pygame.draw.rect(self.screen, color, inner, border_radius=10)
            else:
                button.draw(self.screen)

        for key, button in self.action_buttons.items():
            if key == "home":
                draw_home_button(self.screen, button.rect)
            else:
                if key in {"new", "undo", "redo"}:
                    button.draw(self.screen, self.font)
                elif key == "recall" and button.image is None:
                    button.draw(self.screen, self.font)
                else:
                    button.draw(self.screen)

        if self.recall_open:
            self._draw_recall_overlay()

        pygame.display.flip()

    def run(self, *, quit_on_exit: bool = True) -> None:
        running = True
        self._render()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if self.recall_open:
                    self._handle_recall_event(event)
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif is_primary_pointer_event(event, is_down=True):
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
                elif is_primary_pointer_event(event, is_down=False):
                    self.pointer_down = False
                    self._handle_pointer_up()

            now = time.monotonic()
            if now - self.last_autosave >= self.autosave_interval:
                self._autosave_latest()
                self.last_autosave = now

            self._render()
            self.clock.tick(60)

        if quit_on_exit:
            pygame.quit()


def main() -> None:
    try:
        PaintApp().run(quit_on_exit=True)
    except Exception:
        pygame.quit()


def run_embedded(screen: pygame.Surface, screen_rect: pygame.Rect, clock: pygame.time.Clock) -> None:
    PaintApp(screen=screen, screen_rect=screen_rect, clock=clock).run(quit_on_exit=False)


if __name__ == "__main__":
    main()
