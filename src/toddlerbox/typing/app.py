from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

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


@dataclass
class Glyph:
    char: str
    size: int
    style: str


@dataclass
class EditOp:
    kind: str
    row: int
    col: int
    glyph: Optional[Glyph] = None
    newline: bool = False
    cursor_row: int = 0
    cursor_col: int = 0


@dataclass
class RecallSession:
    label: str
    preview: str
    rich_lines: List[List[Glyph]]
    is_current: bool = False


def _preview_text(text: str, limit: int = 150) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


def _create_text_font(size: int, style: str = "plain") -> pygame.font.Font:
    bold = style == "bold"
    italic = style == "italic"
    if pygame.font.match_font("ubuntu"):
        return pygame.font.SysFont("ubuntu", size, bold=bold, italic=italic)
    return pygame.font.SysFont("sans", size, bold=bold, italic=italic)


def _serialize_rich_lines(lines: List[List[Glyph]]) -> List[List[dict]]:
    return [
        [{"char": glyph.char, "size": glyph.size, "style": glyph.style} for glyph in line]
        for line in lines
    ]


def _deserialize_rich_lines(payload: object) -> Optional[List[List[Glyph]]]:
    if not isinstance(payload, list):
        return None
    parsed: List[List[Glyph]] = []
    for raw_line in payload:
        if not isinstance(raw_line, list):
            return None
        parsed_line: List[Glyph] = []
        for raw_glyph in raw_line:
            if not isinstance(raw_glyph, dict):
                return None
            char = raw_glyph.get("char")
            size = raw_glyph.get("size")
            style = raw_glyph.get("style")
            if not isinstance(char, str) or len(char) != 1:
                return None
            if not isinstance(size, int) or size <= 0:
                return None
            if style not in {"plain", "bold", "italic"}:
                return None
            parsed_line.append(Glyph(char=char, size=size, style=style))
        parsed.append(parsed_line)
    return parsed if parsed else [[]]


def _clone_rich_lines(lines: List[List[Glyph]]) -> List[List[Glyph]]:
    return [[Glyph(char=g.char, size=g.size, style=g.style) for g in line] for line in lines]


def _rich_to_text(lines: List[List[Glyph]]) -> str:
    return "\n".join("".join(g.char for g in line) for line in lines)


def _load_recent_sessions(path: Path, *, limit: int = 200) -> List[RecallSession]:
    if not path.exists():
        return []
    recent: Deque[RecallSession] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rich_lines = _deserialize_rich_lines(record.get("rich_lines"))
                if rich_lines is None:
                    continue
                text = _rich_to_text(rich_lines)
                label = str(record.get("timestamp") or "Saved")
                recent.append(
                    RecallSession(
                        label=label,
                        preview=_preview_text(text),
                        rich_lines=rich_lines,
                    )
                )
    except OSError:
        return []
    return list(reversed(recent))


class TypingApp:
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
        self.typing_dir = dirs["typing"]
        self.sessions_path = self.typing_dir / "sessions.jsonl"

        if screen is None:
            self.screen, self.screen_rect = create_fullscreen_window()
        else:
            self.screen = screen
            self.screen_rect = screen_rect or screen.get_rect()
        self.clock = clock or pygame.time.Clock()

        self.ui_font = pygame.font.SysFont("sans", 20)
        self.default_text_size = 25
        self.size_values = [self.default_text_size, self.default_text_size * 2, self.default_text_size * 4]
        self.text_style = "plain"
        self.current_text_size = self.default_text_size
        self.font_cache: Dict[Tuple[int, str], pygame.font.Font] = {}
        self.size_sample_fonts = {size: _create_text_font(size, "plain") for size in self.size_values}
        self.default_line_style = (self.default_text_size, "plain")

        self.rich_lines: List[List[Glyph]] = [[]]
        self.line_styles: List[Tuple[int, str]] = [self.default_line_style]
        self.text_lines: List[str] = [""]
        self.undo_stack: List[EditOp] = []
        self.cursor_row = 0
        self.cursor_col = 0

        self.margin = 16
        self.menu_pad = 10
        self.menu_gap = 10
        self.menu_bg = (238, 234, 226)
        self.tool_size = max(44, min(56, int(self.screen_rect.height * 0.06)))
        base_panel_width = self.tool_size * 2 + self.menu_gap + self.menu_pad * 2
        panel_width = min(self.screen_rect.width - (self.margin * 3 + 240), base_panel_width * 2)
        self.controls_rect = pygame.Rect(
            self.margin,
            self.margin,
            max(220, panel_width),
            self.screen_rect.height - 2 * self.margin,
        )
        self.text_rect = pygame.Rect(
            self.controls_rect.right + self.margin,
            self.margin,
            self.screen_rect.width - self.controls_rect.width - 3 * self.margin,
            self.screen_rect.height - 2 * self.margin,
        )

        home_size = max(40, int(self.tool_size * 0.85))
        self.home_button = Button(
            rect=pygame.Rect(
                self.screen_rect.right - self.margin - home_size,
                self.margin,
                home_size,
                home_size,
            ),
            fill=self.menu_bg,
        )

        inner_w = self.controls_rect.width - self.menu_pad * 2
        left = self.controls_rect.left + self.menu_pad
        top = self.controls_rect.top + self.menu_pad
        action_h = self.ui_font.get_height() + 16
        self.new_button = Button(
            rect=pygame.Rect(left, top, inner_w, action_h),
            label="New",
            fill=(245, 245, 245),
        )
        self.undo_button = Button(
            rect=pygame.Rect(left, self.new_button.rect.bottom + self.menu_gap, inner_w, action_h),
            label="Undo",
            fill=(245, 245, 245),
        )

        tri_gap = max(6, self.menu_gap // 2)
        tri_w = max(1, (inner_w - tri_gap * 2) // 3)
        size_top = self.undo_button.rect.bottom + self.menu_gap
        size_h = max(120, int(self.default_text_size * 4.8))
        self.size_buttons: Dict[int, Button] = {}
        for idx, size in enumerate(self.size_values):
            rect = pygame.Rect(left + idx * (tri_w + tri_gap), size_top, tri_w, size_h)
            self.size_buttons[size] = Button(rect=rect, fill=(245, 245, 245))

        style_top = size_top + size_h + self.menu_gap
        self.style_buttons: Dict[str, Button] = {}
        for idx, (style, label) in enumerate([("plain", "Plain"), ("bold", "Bold"), ("italic", "Italic")]):
            rect = pygame.Rect(left + idx * (tri_w + tri_gap), style_top, tri_w, action_h)
            self.style_buttons[style] = Button(rect=rect, label=label, fill=(245, 245, 245))

        recall_top = style_top + action_h + self.menu_gap
        recall_h = min(inner_w, max(80, self.controls_rect.bottom - self.menu_pad - recall_top))
        self.recall_button = Button(
            rect=pygame.Rect(left, recall_top, inner_w, recall_h),
            label="Recall",
            fill=self.menu_bg,
        )

        self.recall_open = False
        self.recall_items: List[RecallSession] = []
        self.recall_strip_rect = self.controls_rect.copy()
        self.recall_scroll_y = 0
        self.recall_max_scroll = 0
        self.recall_item_padding_x = 12
        self.recall_item_gap = 12
        self.recall_item_height = max(120, int(self.controls_rect.height * 0.2))
        self.recall_drag_last_y: Optional[int] = None
        self.recall_pressed_index: Optional[int] = None
        self.recall_drag_distance = 0

        self.text_pad_x = 24
        self.text_pad_top = 20
        self.line_gap = 6
        self.recall_button.image = self._build_recall_button_thumbnail()

    def _get_font(self, size: int, style: str) -> pygame.font.Font:
        key = (size, style)
        cached = self.font_cache.get(key)
        if cached is not None:
            return cached
        font = _create_text_font(size, style)
        self.font_cache[key] = font
        return font

    def _line_text(self, row: int) -> str:
        return "".join(g.char for g in self.rich_lines[row])

    def _sync_text_line(self, row: int) -> None:
        self.text_lines[row] = self._line_text(row)

    def _sync_all_text_lines(self) -> None:
        self.text_lines = ["".join(g.char for g in line) for line in self.rich_lines]
        if not self.text_lines:
            self.text_lines = [""]
            self.rich_lines = [[]]
            self.line_styles = [self.default_line_style]
            return
        prior_styles = self.line_styles if hasattr(self, "line_styles") else []
        next_styles: List[Tuple[int, str]] = []
        for idx, line in enumerate(self.rich_lines):
            if line:
                last = line[-1]
                next_styles.append((last.size, last.style))
            elif idx < len(prior_styles):
                next_styles.append(prior_styles[idx])
            else:
                next_styles.append(self.default_line_style)
        self.line_styles = next_styles

    def _push_undo(self, op: EditOp) -> None:
        self.undo_stack.append(op)
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def _insert_newline_at(self, row: int, col: int) -> None:
        left = self.rich_lines[row][:col]
        right = self.rich_lines[row][col:]
        self.rich_lines[row] = left
        self.rich_lines.insert(row + 1, right)
        if left:
            self.line_styles[row] = (left[-1].size, left[-1].style)
        if right:
            right_style = (right[-1].size, right[-1].style)
        else:
            right_style = (self.current_text_size, self.text_style)
        self.line_styles.insert(row + 1, right_style)
        self.text_lines[row] = "".join(g.char for g in left)
        self.text_lines.insert(row + 1, "".join(g.char for g in right))

    def _remove_newline_at(self, row: int) -> None:
        if row + 1 >= len(self.rich_lines):
            return
        self.rich_lines[row].extend(self.rich_lines[row + 1])
        self.rich_lines.pop(row + 1)
        if len(self.line_styles) > row + 1:
            self.line_styles.pop(row + 1)
        if self.rich_lines[row]:
            last = self.rich_lines[row][-1]
            self.line_styles[row] = (last.size, last.style)
        self.text_lines[row] = "".join(g.char for g in self.rich_lines[row])
        self.text_lines.pop(row + 1)

    def _insert_glyph_at(self, row: int, col: int, glyph: Glyph) -> None:
        self.rich_lines[row].insert(col, Glyph(char=glyph.char, size=glyph.size, style=glyph.style))
        self.line_styles[row] = (glyph.size, glyph.style)
        self._sync_text_line(row)

    def _remove_glyph_at(self, row: int, col: int) -> Optional[Glyph]:
        if col < 0 or col >= len(self.rich_lines[row]):
            return None
        removed = self.rich_lines[row].pop(col)
        self._sync_text_line(row)
        return removed

    def _insert_char(self, char: str) -> None:
        if char == "\n":
            op = EditOp(
                kind="insert",
                row=self.cursor_row,
                col=self.cursor_col,
                newline=True,
                cursor_row=self.cursor_row,
                cursor_col=self.cursor_col,
            )
            self._insert_newline_at(self.cursor_row, self.cursor_col)
            self.cursor_row += 1
            self.cursor_col = 0
            self._push_undo(op)
            return

        glyph = Glyph(char=char, size=self.current_text_size, style=self.text_style)
        op = EditOp(
            kind="insert",
            row=self.cursor_row,
            col=self.cursor_col,
            glyph=Glyph(char=glyph.char, size=glyph.size, style=glyph.style),
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._insert_glyph_at(self.cursor_row, self.cursor_col, glyph)
        self.cursor_col += 1
        self._push_undo(op)

    def _delete_backward(self) -> EditOp | None:
        if self.cursor_row == 0 and self.cursor_col == 0:
            return None
        if self.cursor_col > 0:
            removed = self._remove_glyph_at(self.cursor_row, self.cursor_col - 1)
            if removed is None:
                return None
            op = EditOp(
                kind="delete",
                row=self.cursor_row,
                col=self.cursor_col - 1,
                glyph=Glyph(char=removed.char, size=removed.size, style=removed.style),
                cursor_row=self.cursor_row,
                cursor_col=self.cursor_col,
            )
            self.cursor_col -= 1
            return op

        prev_len = len(self.rich_lines[self.cursor_row - 1])
        op = EditOp(
            kind="delete",
            row=self.cursor_row - 1,
            col=prev_len,
            newline=True,
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._remove_newline_at(self.cursor_row - 1)
        self.cursor_row -= 1
        self.cursor_col = prev_len
        return op

    def _undo(self) -> None:
        if not self.undo_stack:
            return
        op = self.undo_stack.pop()
        if op.kind == "insert":
            if op.newline:
                self._remove_newline_at(op.row)
            else:
                self._remove_glyph_at(op.row, op.col)
        else:
            if op.newline:
                self._insert_newline_at(op.row, op.col)
            elif op.glyph is not None:
                self._insert_glyph_at(op.row, op.col, op.glyph)
        self.cursor_row = op.cursor_row
        self.cursor_col = op.cursor_col

    def _archive_session(self) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rich_lines": _serialize_rich_lines(self.rich_lines),
        }
        with self.sessions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _current_text(self) -> str:
        return "\n".join(self.text_lines).rstrip()

    def _clear_text(self) -> None:
        self.rich_lines = [[]]
        self.line_styles = [self.default_line_style]
        self.text_lines = [""]
        self.undo_stack = []
        self.cursor_row = 0
        self.cursor_col = 0

    def _move_cursor_left(self) -> None:
        if self.cursor_col > 0:
            self.cursor_col -= 1
            return
        if self.cursor_row > 0:
            self.cursor_row -= 1
            self.cursor_col = len(self.rich_lines[self.cursor_row])

    def _move_cursor_right(self) -> None:
        line = self.rich_lines[self.cursor_row]
        if self.cursor_col < len(line):
            self.cursor_col += 1
            return
        if self.cursor_row < len(self.rich_lines) - 1:
            self.cursor_row += 1
            self.cursor_col = 0

    def _move_cursor_up(self) -> None:
        if self.cursor_row == 0:
            return
        self.cursor_row -= 1
        self.cursor_col = min(self.cursor_col, len(self.rich_lines[self.cursor_row]))

    def _move_cursor_down(self) -> None:
        if self.cursor_row >= len(self.rich_lines) - 1:
            return
        self.cursor_row += 1
        self.cursor_col = min(self.cursor_col, len(self.rich_lines[self.cursor_row]))

    def _move_cursor_home(self) -> None:
        self.cursor_col = 0

    def _move_cursor_end(self) -> None:
        self.cursor_col = len(self.rich_lines[self.cursor_row])

    def _move_cursor_page_up(self, lines: int) -> None:
        if self.cursor_row == 0:
            return
        self.cursor_row = max(0, self.cursor_row - lines)
        self.cursor_col = min(self.cursor_col, len(self.rich_lines[self.cursor_row]))

    def _move_cursor_page_down(self, lines: int) -> None:
        if self.cursor_row >= len(self.rich_lines) - 1:
            return
        self.cursor_row = min(len(self.rich_lines) - 1, self.cursor_row + lines)
        self.cursor_col = min(self.cursor_col, len(self.rich_lines[self.cursor_row]))

    def _build_recall_button_thumbnail(self) -> pygame.Surface:
        size = self.recall_button.rect.size
        thumb = pygame.Surface((max(1, size[0] - 6), max(1, size[1] - 6)))
        thumb.fill((248, 248, 248))
        pygame.draw.rect(thumb, (120, 120, 120), thumb.get_rect(), width=2)
        preview_font = pygame.font.SysFont("sans", max(14, self.ui_font.get_height() - 2))
        message = "I'm Rosie's ToddlerBox. Touch here to see what you've written."
        max_width = thumb.get_width() - 16
        words = message.split(" ")
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if preview_font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        y = 10
        for line in lines:
            if y + preview_font.get_height() > thumb.get_height() - 8:
                break
            surf = preview_font.render(line, True, (40, 40, 40))
            thumb.blit(surf, (8, y))
            y += preview_font.get_height() + 4
        return thumb

    def _line_step(self) -> int:
        return self.current_text_size + self.line_gap

    def _lines_per_page(self) -> int:
        return max(1, (self.text_rect.height - (self.text_pad_top + 20)) // self._line_step())

    def _set_text_font(self, *, size: Optional[int] = None, style: Optional[str] = None) -> None:
        if size is not None:
            self.current_text_size = size
        if style is not None:
            self.text_style = style

    def _line_font_height(self, row: int, *, for_cursor_row: bool = False) -> int:
        line = self.rich_lines[row]
        if not line:
            if for_cursor_row:
                return self._get_font(self.current_text_size, self.text_style).get_height()
            size, style = self.line_styles[row]
            return self._get_font(size, style).get_height()
        return max(self._get_font(g.size, g.style).get_height() for g in line)

    def _open_recall(self) -> None:
        self.recall_strip_rect = self.controls_rect.copy()
        self.recall_items = [
            RecallSession(
                label="Current",
                preview=_preview_text(self._current_text()),
                rich_lines=_clone_rich_lines(self.rich_lines),
                is_current=True,
            )
        ]
        self.recall_items.extend(_load_recent_sessions(self.sessions_path))
        self.recall_scroll_y = 0
        self.recall_drag_last_y = None
        self.recall_pressed_index = None
        self.recall_drag_distance = 0
        self.recall_max_scroll = self._recall_max_scroll()
        self.recall_open = True

    def _recall_max_scroll(self) -> int:
        total_height = len(self.recall_items) * (self.recall_item_height + self.recall_item_gap) + self.recall_item_gap
        return max(0, total_height - self.recall_strip_rect.height)

    def _scroll_recall(self, delta: int) -> None:
        self.recall_scroll_y = max(0, min(self.recall_max_scroll, self.recall_scroll_y + delta))

    def _recall_item_rect(self, index: int) -> pygame.Rect:
        y = self.recall_item_gap - self.recall_scroll_y + index * (self.recall_item_height + self.recall_item_gap)
        return pygame.Rect(
            self.recall_strip_rect.left + self.recall_item_padding_x,
            self.recall_strip_rect.top + y,
            self.recall_strip_rect.width - self.recall_item_padding_x * 2,
            self.recall_item_height,
        )

    def _recall_index_at_pos(self, pos: Tuple[int, int]) -> Optional[int]:
        for idx, _ in enumerate(self.recall_items):
            if self._recall_item_rect(idx).collidepoint(pos):
                return idx
        return None

    def _apply_recall(self, index: int) -> None:
        item = self.recall_items[index]
        if item.is_current:
            self.recall_open = False
            return
        self.rich_lines = _clone_rich_lines(item.rich_lines)
        self._sync_all_text_lines()
        self.undo_stack = []
        self.cursor_row = max(0, len(self.rich_lines) - 1)
        self.cursor_col = len(self.rich_lines[self.cursor_row]) if self.rich_lines else 0
        self.recall_open = False

    def _wrap_preview_lines(self, text: str, max_width: int, max_lines: int) -> List[str]:
        if not text:
            return ["(empty)"]
        words = text.split(" ")
        if not words:
            return ["(empty)"]
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if self.ui_font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if len(lines) < max_lines and current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        return lines

    def _handle_recall_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.recall_open = False
            return
        if is_primary_pointer_event(event, is_down=True):
            pos = pointer_event_pos(event, self.screen_rect)
            if pos is None:
                return
            if not self.recall_strip_rect.collidepoint(pos):
                self.recall_open = False
                self.recall_drag_last_y = None
                self.recall_pressed_index = None
                self.recall_drag_distance = 0
                return
            self.recall_drag_last_y = pos[1]
            self.recall_pressed_index = self._recall_index_at_pos(pos)
            self.recall_drag_distance = 0
            return
        if event.type == pygame.MOUSEMOTION and self.recall_drag_last_y is not None:
            dy = event.pos[1] - self.recall_drag_last_y
            self._scroll_recall(-dy)
            self.recall_drag_distance += abs(dy)
            self.recall_drag_last_y = event.pos[1]
            return
        if is_primary_pointer_event(event, is_down=False):
            pos = pointer_event_pos(event, self.screen_rect)
            if pos is None:
                return
            if (
                self.recall_pressed_index is not None
                and self.recall_drag_distance < 10
                and self._recall_index_at_pos(pos) == self.recall_pressed_index
            ):
                self._apply_recall(self.recall_pressed_index)
            self.recall_drag_last_y = None
            self.recall_pressed_index = None
            self.recall_drag_distance = 0
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.recall_strip_rect.collidepoint(pygame.mouse.get_pos()):
                self._scroll_recall(-event.y * 40)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in {4, 5}:
            if self.recall_strip_rect.collidepoint(event.pos):
                self._scroll_recall(-40 if event.button == 4 else 40)

    def _draw_recall_overlay(self) -> None:
        overlay = pygame.Surface(self.screen_rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (230, 230, 230), self.recall_strip_rect)

        preview_x_pad = 10
        preview_y_pad = 10
        for idx, item in enumerate(self.recall_items):
            rect = self._recall_item_rect(idx)
            if rect.bottom < self.recall_strip_rect.top or rect.top > self.recall_strip_rect.bottom:
                continue
            pygame.draw.rect(self.screen, (248, 248, 248), rect)
            border = (200, 60, 60) if item.is_current else (120, 120, 120)
            pygame.draw.rect(self.screen, border, rect, width=3 if item.is_current else 2)

            label_surface = self.ui_font.render(item.label, True, (30, 30, 30))
            self.screen.blit(label_surface, (rect.left + preview_x_pad, rect.top + preview_y_pad))

            preview_top = rect.top + preview_y_pad + self.ui_font.get_height() + 6
            max_width = rect.width - preview_x_pad * 2
            available_height = rect.bottom - preview_top - preview_y_pad
            line_step = self.ui_font.get_height() + 4
            max_lines = max(1, available_height // line_step)
            lines = self._wrap_preview_lines(item.preview, max_width, max_lines)
            for line_idx, line in enumerate(lines):
                y = preview_top + line_idx * line_step
                if y + self.ui_font.get_height() > rect.bottom - preview_y_pad:
                    break
                line_surface = self.ui_font.render(line, True, (40, 40, 40))
                self.screen.blit(line_surface, (rect.left + preview_x_pad, y))

    def _render(self) -> None:
        self.screen.fill((248, 248, 248))

        pygame.draw.rect(self.screen, self.menu_bg, self.controls_rect)
        pygame.draw.rect(self.screen, (255, 255, 255), self.text_rect)
        pygame.draw.rect(self.screen, (200, 200, 200), self.text_rect, width=2)

        draw_home_button(self.screen, self.home_button.rect)
        self.new_button.draw(self.screen, self.ui_font)
        self.undo_button.draw(self.screen, self.ui_font)
        for size, button in self.size_buttons.items():
            button.draw(self.screen)
            sample = self.size_sample_fonts[size].render("A", True, (25, 25, 25))
            sample_rect = sample.get_rect(center=button.rect.center)
            self.screen.blit(sample, sample_rect)
            if size == self.current_text_size:
                pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3, border_radius=12)
        for style, button in self.style_buttons.items():
            button.draw(self.screen, self.ui_font)
            if style == self.text_style:
                pygame.draw.rect(self.screen, (200, 60, 60), button.rect, width=3, border_radius=12)
        if self.recall_button.image is None:
            self.recall_button.draw(self.screen, self.ui_font)
        else:
            self.recall_button.draw(self.screen)

        text_x = self.text_rect.left + self.text_pad_x
        y = self.text_rect.top + self.text_pad_top
        cursor_x = text_x
        cursor_y = y
        cursor_h = self._line_font_height(self.cursor_row)

        for row_idx, line in enumerate(self.rich_lines):
            x = text_x
            row_h = self._line_font_height(row_idx)
            if row_idx == self.cursor_row:
                cursor_x = text_x
                cursor_y = y
                cursor_h = row_h
            for col_idx, glyph in enumerate(line):
                font = self._get_font(glyph.size, glyph.style)
                surf = font.render(glyph.char, True, (20, 20, 20))
                glyph_y = y + (row_h - font.get_height())
                self.screen.blit(surf, (x, glyph_y))
                glyph_w = font.size(glyph.char)[0]
                if row_idx == self.cursor_row and col_idx < self.cursor_col:
                    cursor_x = x + glyph_w
                x += glyph_w
            if row_idx == self.cursor_row and self.cursor_col >= len(line):
                cursor_x = x
            y += row_h + self.line_gap

        pygame.draw.rect(self.screen, (30, 30, 30), (cursor_x, cursor_y, 6, cursor_h))

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
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_BACKSPACE:
                        op = self._delete_backward()
                        if op:
                            self._push_undo(op)
                    elif event.key == pygame.K_RETURN:
                        self._insert_char("\n")
                    elif event.key in {
                        pygame.K_LEFT,
                        pygame.K_RIGHT,
                        pygame.K_UP,
                        pygame.K_DOWN,
                        pygame.K_HOME,
                        pygame.K_END,
                        pygame.K_PAGEUP,
                        pygame.K_PAGEDOWN,
                    }:
                        if event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI):
                            continue
                        if event.key == pygame.K_LEFT:
                            self._move_cursor_left()
                        elif event.key == pygame.K_RIGHT:
                            self._move_cursor_right()
                        elif event.key == pygame.K_UP:
                            self._move_cursor_up()
                        elif event.key == pygame.K_DOWN:
                            self._move_cursor_down()
                        elif event.key == pygame.K_HOME:
                            self._move_cursor_home()
                        elif event.key == pygame.K_END:
                            self._move_cursor_end()
                        elif event.key == pygame.K_PAGEUP:
                            self._move_cursor_page_up(self._lines_per_page())
                        elif event.key == pygame.K_PAGEDOWN:
                            self._move_cursor_page_down(self._lines_per_page())
                    elif event.key in {pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_LALT, pygame.K_RALT}:
                        continue
                    elif event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI):
                        continue
                    else:
                        if event.unicode and event.unicode.isprintable():
                            self._insert_char(event.unicode)
                elif is_primary_pointer_event(event, is_down=True):
                    pos = pointer_event_pos(event, self.screen_rect)
                    if pos is None:
                        continue
                    if self.home_button.hit(pos):
                        running = False
                    elif self.new_button.hit(pos):
                        self._archive_session()
                        self._clear_text()
                    elif self.undo_button.hit(pos):
                        self._undo()
                    elif self.recall_button.hit(pos):
                        self._open_recall()
                    else:
                        handled = False
                        for size, button in self.size_buttons.items():
                            if button.hit(pos):
                                self._set_text_font(size=size)
                                handled = True
                                break
                        if handled:
                            continue
                        for style, button in self.style_buttons.items():
                            if button.hit(pos):
                                self._set_text_font(style=style)
                                handled = True
                                break
                        if handled:
                            continue

            self._render()
            self.clock.tick(60)

        if quit_on_exit:
            pygame.quit()


def main() -> None:
    try:
        TypingApp().run(quit_on_exit=True)
    except Exception:
        pygame.quit()


def run_embedded(screen: pygame.Surface, screen_rect: pygame.Rect, clock: pygame.time.Clock) -> None:
    TypingApp(screen=screen, screen_rect=screen_rect, clock=clock).run(quit_on_exit=False)


if __name__ == "__main__":
    main()
