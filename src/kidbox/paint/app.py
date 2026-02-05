from __future__ import annotations

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


@dataclass
class Brush:
    name: str
    kind: str
    size: int


@dataclass
class Stroke:
    brush: Brush
    color: Color
    points: List[Point]


def _save_surface_atomic(surface: pygame.Surface, path: Path) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    pygame.image.save(surface, str(tmp_path))
    os.replace(tmp_path, path)


def _list_archives(paint_dir: Path) -> List[Path]:
    files = []
    for candidate in paint_dir.glob("*.png"):
        if candidate.name == "latest.png":
            continue
        files.append(candidate)
    files.sort(reverse=True)
    return files


def _draw_stamp(surface: pygame.Surface, brush: Brush, color: Color, pos: Point, pressure: float = 1.0) -> None:
    x, y = pos
    size = max(2, int(brush.size * pressure))
    if brush.kind == "round":
        pygame.draw.circle(surface, color, pos, size // 2)
    elif brush.kind == "square":
        rect = pygame.Rect(x - size // 2, y - size // 2, size, size)
        pygame.draw.rect(surface, color, rect)
    elif brush.kind == "triangle":
        half = size // 2
        points = [(x, y - half), (x - half, y + half), (x + half, y + half)]
        pygame.draw.polygon(surface, color, points)
    elif brush.kind == "star":
        radius = size // 2
        points = []
        for i in range(6):
            angle = i * 60
            r = radius if i % 2 == 0 else radius // 2
            px = x + int(r * pygame.math.Vector2(1, 0).rotate(angle).x)
            py = y + int(r * pygame.math.Vector2(1, 0).rotate(angle).y)
            points.append((px, py))
        pygame.draw.polygon(surface, color, points)
    elif brush.kind == "textured":
        for offset in range(6):
            jitter_x = x + (offset - 3)
            jitter_y = y + ((offset % 3) - 1)
            alpha = 120
            stamp = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(stamp, (*color, alpha), (size // 2, size // 2), size // 3)
            surface.blit(stamp, (jitter_x - size // 2, jitter_y - size // 2))
    else:
        pygame.draw.circle(surface, color, pos, size // 2)


def _draw_segment(surface: pygame.Surface, stroke: Stroke, start: Point, end: Point) -> None:
    distance = max(1, pygame.math.Vector2(end).distance_to(start))
    steps = max(1, int(distance / 2))
    for idx in range(steps + 1):
        t = idx / steps
        x = int(start[0] + (end[0] - start[0]) * t)
        y = int(start[1] + (end[1] - start[1]) * t)
        pressure = 1.0
        if stroke.brush.kind == "fountain":
            pressure = max(0.3, min(1.2, 1.2 - (distance / 30)))
        _draw_stamp(surface, stroke.brush, stroke.color, (x, y), pressure=pressure)


def _rebuild_canvas(base: pygame.Surface, strokes: List[Stroke]) -> pygame.Surface:
    canvas = base.copy()
    for stroke in strokes:
        for idx in range(1, len(stroke.points)):
            _draw_segment(canvas, stroke, stroke.points[idx - 1], stroke.points[idx])
    return canvas


class PaintApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.data_root = get_data_root(self.config)
        dirs = ensure_directories(self.data_root)
        self.paint_dir = dirs["paint"]

        self.screen, self.screen_rect = create_fullscreen_window()
        self.clock = pygame.time.Clock()

        self.margin = 16
        controls_height = max(140, int(self.screen_rect.height * 0.22))
        self.canvas_rect = pygame.Rect(
            self.margin,
            self.margin,
            self.screen_rect.width - 2 * self.margin,
            self.screen_rect.height - controls_height - 2 * self.margin,
        )
        self.controls_rect = pygame.Rect(
            self.margin,
            self.canvas_rect.bottom + self.margin,
            self.screen_rect.width - 2 * self.margin,
            controls_height - self.margin,
        )

        self.base_surface = pygame.Surface(self.canvas_rect.size)
        self.base_surface.fill((255, 255, 255))
        self.canvas_surface = self.base_surface.copy()

        self.palette = [tuple(color) for color in self.config.get("paint", {}).get("palette", [])]
        self.current_color: Color = self.palette[0] if self.palette else (0, 0, 0)

        base_size = max(16, int(self.canvas_rect.width * 0.02))
        self.brushes = [
            Brush("Round S", "round", base_size),
            Brush("Round M", "round", base_size * 2),
            Brush("Round L", "round", base_size * 3),
            Brush("Square", "square", base_size * 2),
            Brush("Triangle", "triangle", base_size * 2),
            Brush("Star", "star", base_size * 2),
            Brush("Fountain", "fountain", base_size * 2),
            Brush("Texture", "textured", base_size * 2),
        ]
        self.current_brush = self.brushes[0]

        self.strokes: List[Stroke] = []
        self.current_stroke: Optional[Stroke] = None

        self.font = pygame.font.SysFont("sans", 18)
        self.last_autosave = time.monotonic()
        self.autosave_interval = int(self.config.get("paint", {}).get("autosave_seconds", 10))

        self.action_buttons: Dict[str, Button] = {}
        self.brush_buttons: List[Button] = []
        self.palette_buttons: List[Button] = []
        self.thumbnail_button: Optional[Button] = None
        self._build_ui()

        self.recall_open = False
        self.recall_scroll = 0
        self.recall_thumbnails: List[Tuple[pygame.Surface, pygame.Rect, Path]] = []
        self.recall_strip_rect = pygame.Rect(0, 0, 0, 0)
        self.recall_max_scroll = 0

    def _build_ui(self) -> None:
        action_width = max(160, int(self.controls_rect.width * 0.18))
        actions_rect = pygame.Rect(
            self.controls_rect.right - action_width,
            self.controls_rect.top,
            action_width,
            self.controls_rect.height,
        )
        main_rect = pygame.Rect(
            self.controls_rect.left,
            self.controls_rect.top,
            self.controls_rect.width - action_width - self.margin,
            self.controls_rect.height,
        )

        button_height = max(44, int(actions_rect.height / 4) - 8)
        button_width = actions_rect.width - 16
        for idx, name in enumerate(["Home", "Undo", "New", "Recall"]):
            rect = pygame.Rect(
                actions_rect.left + 8,
                actions_rect.top + 8 + idx * (button_height + 8),
                button_width,
                button_height,
            )
            self.action_buttons[name.lower()] = Button(rect=rect, label=name, fill=(240, 240, 240))

        brush_row = pygame.Rect(main_rect.left, main_rect.top, main_rect.width, main_rect.height // 2)
        palette_row = pygame.Rect(main_rect.left, brush_row.bottom, main_rect.width, main_rect.height - brush_row.height)

        brush_gap = 8
        brush_width = max(70, int((brush_row.width - brush_gap * (len(self.brushes) - 1)) / len(self.brushes)))
        for idx, brush in enumerate(self.brushes):
            rect = pygame.Rect(
                brush_row.left + idx * (brush_width + brush_gap),
                brush_row.top + 6,
                brush_width,
                brush_row.height - 12,
            )
            self.brush_buttons.append(Button(rect=rect, label=brush.name, fill=(250, 250, 250)))

        palette_cols = 8
        palette_rows = 2
        swatch_gap = 8
        swatch_width = (palette_row.width - swatch_gap * (palette_cols - 1)) // palette_cols
        swatch_height = (palette_row.height - swatch_gap * (palette_rows - 1)) // palette_rows
        for row in range(palette_rows):
            for col in range(palette_cols):
                idx = row * palette_cols + col
                if idx >= len(self.palette):
                    continue
                rect = pygame.Rect(
                    palette_row.left + col * (swatch_width + swatch_gap),
                    palette_row.top + row * (swatch_height + swatch_gap),
                    swatch_width,
                    swatch_height,
                )
                self.palette_buttons.append(Button(rect=rect, fill=self.palette[idx]))

        self._update_thumbnail_button()

    def _update_thumbnail_button(self) -> None:
        archives = _list_archives(self.paint_dir)
        if not archives:
            self.thumbnail_button = None
            return
        latest_archive = archives[0]
        thumb = pygame.image.load(str(latest_archive)).convert_alpha()
        size = self.action_buttons["recall"].rect.size
        thumb = pygame.transform.smoothscale(thumb, size)
        button = Button(rect=self.action_buttons["recall"].rect.copy(), image=thumb, fill=(235, 235, 235))
        self.thumbnail_button = button

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
        self.strokes = []

    def _open_recall(self) -> None:
        archives = _list_archives(self.paint_dir)
        if not archives:
            return
        thumb_size = 140
        padding = 16
        strip_height = thumb_size + padding * 2
        self.recall_strip_rect = pygame.Rect(0, (self.screen_rect.height - strip_height) // 2, self.screen_rect.width, strip_height)
        self.recall_thumbnails = []
        x = padding
        for path in archives:
            image = pygame.image.load(str(path)).convert_alpha()
            image = pygame.transform.smoothscale(image, (thumb_size, thumb_size))
            rect = pygame.Rect(x, self.recall_strip_rect.top + padding, thumb_size, thumb_size)
            self.recall_thumbnails.append((image, rect, path))
            x += thumb_size + padding
        self.recall_scroll = 0
        self.recall_max_scroll = max(0, x - self.screen_rect.width)
        self.recall_open = True

    def _handle_recall_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.recall_open = False
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.recall_strip_rect.collidepoint(event.pos):
                self.recall_open = False
                return
            for image, rect, path in self.recall_thumbnails:
                moved_rect = rect.move(-self.recall_scroll, 0)
                if moved_rect.collidepoint(event.pos):
                    loaded = pygame.image.load(str(path)).convert_alpha()
                    loaded = pygame.transform.smoothscale(loaded, self.canvas_rect.size)
                    self.base_surface.blit(loaded, (0, 0))
                    self.canvas_surface = self.base_surface.copy()
                    self.strokes = []
                    self.recall_open = False
                    return
        if event.type == pygame.MOUSEWHEEL:
            delta = event.x if event.x != 0 else -event.y
            new_scroll = self.recall_scroll - delta * 40
            self.recall_scroll = max(0, min(self.recall_max_scroll, new_scroll))
        if event.type == pygame.MOUSEMOTION and event.buttons[0]:
            new_scroll = self.recall_scroll - event.rel[0]
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
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.canvas_rect.collidepoint(event.pos):
                        local_pos = (event.pos[0] - self.canvas_rect.left, event.pos[1] - self.canvas_rect.top)
                        self.current_stroke = Stroke(self.current_brush, self.current_color, [local_pos])
                    else:
                        for idx, button in enumerate(self.brush_buttons):
                            if button.hit(event.pos):
                                self.current_brush = self.brushes[idx]
                        for idx, button in enumerate(self.palette_buttons):
                            if button.hit(event.pos):
                                self.current_color = self.palette[idx]
                        if self.action_buttons["home"].hit(event.pos):
                            running = False
                        elif self.action_buttons["undo"].hit(event.pos):
                            if self.strokes:
                                self.strokes.pop()
                                self.canvas_surface = _rebuild_canvas(self.base_surface, self.strokes)
                        elif self.action_buttons["new"].hit(event.pos):
                            self._archive_current()
                            self._reset_canvas()
                        elif self.action_buttons["recall"].hit(event.pos):
                            if self.thumbnail_button is not None:
                                self._open_recall()
                elif event.type == pygame.MOUSEMOTION and self.current_stroke:
                    if event.buttons[0]:
                        local_pos = (event.pos[0] - self.canvas_rect.left, event.pos[1] - self.canvas_rect.top)
                        last_point = self.current_stroke.points[-1]
                        self.current_stroke.points.append(local_pos)
                        _draw_segment(self.canvas_surface, self.current_stroke, last_point, local_pos)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.current_stroke:
                        if len(self.strokes) >= 10:
                            self.strokes.pop(0)
                        self.strokes.append(self.current_stroke)
                        self.current_stroke = None

            now = time.monotonic()
            if now - self.last_autosave >= self.autosave_interval:
                self._autosave_latest()
                self.last_autosave = now

            self.screen.fill((252, 248, 240))
            self.screen.blit(self.canvas_surface, self.canvas_rect.topleft)
            pygame.draw.rect(self.screen, (200, 200, 200), self.canvas_rect, width=2)

            for idx, button in enumerate(self.brush_buttons):
                button.draw(self.screen, self.font)
                if self.brushes[idx] == self.current_brush:
                    pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3, border_radius=12)

            for idx, button in enumerate(self.palette_buttons):
                button.draw(self.screen)
                if self.palette[idx] == self.current_color:
                    pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3)

            for key, button in self.action_buttons.items():
                if key == "home":
                    draw_home_button(self.screen, button.rect)
                elif key == "recall" and self.thumbnail_button is not None:
                    self.thumbnail_button.draw(self.screen)
                else:
                    button.draw(self.screen, self.font)

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
