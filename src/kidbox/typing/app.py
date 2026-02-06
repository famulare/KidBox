from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import pygame

from kidbox.config import load_config
from kidbox.paths import ensure_directories, get_data_root
from kidbox.ui.common import Button, create_fullscreen_window, draw_home_button


@dataclass
class EditOp:
    kind: str
    row: int
    col: int
    text: str
    cursor_row: int
    cursor_col: int


@dataclass
class RecallSession:
    label: str
    text: str
    preview: str
    is_current: bool = False


def _preview_text(text: str, limit: int = 150) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


def _load_recent_sessions(path: Path, *, limit: int = 200) -> List[Tuple[str, str]]:
    if not path.exists():
        return []
    recent: Deque[Tuple[str, str]] = deque(maxlen=limit)
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
                text = record.get("text")
                if not isinstance(text, str):
                    continue
                timestamp = record.get("timestamp")
                label = str(timestamp) if timestamp else "Saved"
                recent.append((label, text))
    except OSError:
        return []
    return list(reversed(recent))


class TypingApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.data_root = get_data_root(self.config)
        dirs = ensure_directories(self.data_root)
        self.typing_dir = dirs["typing"]
        self.sessions_path = self.typing_dir / "sessions.jsonl"

        self.screen, self.screen_rect = create_fullscreen_window()
        self.clock = pygame.time.Clock()

        font_size = 20
        self.font = pygame.font.SysFont("sans", font_size)
        self.text_lines: List[str] = [""]
        self.undo_stack: List[EditOp] = []
        self.cursor_row = 0
        self.cursor_col = 0

        button_w = 110
        button_h = 50
        self.home_button = Button(rect=pygame.Rect(20, 20, 70, button_h), fill=(240, 240, 240))
        self.undo_button = Button(
            rect=pygame.Rect(self.screen_rect.width - button_w * 2 - 30, 20, button_w, button_h),
            label="Undo",
            fill=(240, 240, 240),
        )
        self.recall_button = Button(
            rect=pygame.Rect(self.screen_rect.width - button_w * 3 - 40, 20, button_w, button_h),
            label="Recall",
            fill=(240, 240, 240),
        )
        self.new_button = Button(
            rect=pygame.Rect(self.screen_rect.width - button_w - 20, 20, button_w, button_h),
            label="New",
            fill=(240, 240, 240),
        )
        self.margin = 40

        self.recall_open = False
        self.recall_items: List[RecallSession] = []
        self.recall_strip_rect = pygame.Rect(0, 0, max(220, int(self.screen_rect.width * 0.28)), self.screen_rect.height)
        self.recall_scroll_y = 0
        self.recall_max_scroll = 0
        self.recall_item_padding_x = 12
        self.recall_item_gap = 12
        self.recall_item_height = max(120, int(self.screen_rect.height * 0.2))
        self.recall_drag_last_y: Optional[int] = None
        self.recall_pressed_index: Optional[int] = None
        self.recall_drag_distance = 0

    def _push_undo(self, op: EditOp) -> None:
        self.undo_stack.append(op)
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def _insert_text_at(self, row: int, col: int, text: str) -> None:
        if text == "\n":
            line = self.text_lines[row]
            left = line[:col]
            right = line[col:]
            self.text_lines[row] = left
            self.text_lines.insert(row + 1, right)
            return
        line = self.text_lines[row]
        self.text_lines[row] = line[:col] + text + line[col:]

    def _remove_text_at(self, row: int, col: int, text: str) -> None:
        if text == "\n":
            if row + 1 >= len(self.text_lines):
                return
            self.text_lines[row] = self.text_lines[row] + self.text_lines[row + 1]
            self.text_lines.pop(row + 1)
            return
        line = self.text_lines[row]
        self.text_lines[row] = line[:col] + line[col + len(text) :]

    def _insert_char(self, char: str) -> None:
        op = EditOp(
            kind="insert",
            row=self.cursor_row,
            col=self.cursor_col,
            text=char,
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._insert_text_at(self.cursor_row, self.cursor_col, char)
        if char == "\n":
            self.cursor_row += 1
            self.cursor_col = 0
        else:
            self.cursor_col += len(char)
        self._push_undo(op)

    def _delete_backward(self) -> EditOp | None:
        if self.cursor_row == 0 and self.cursor_col == 0:
            return None
        if self.cursor_col > 0:
            line = self.text_lines[self.cursor_row]
            removed = line[self.cursor_col - 1]
            op = EditOp(
                kind="delete",
                row=self.cursor_row,
                col=self.cursor_col - 1,
                text=removed,
                cursor_row=self.cursor_row,
                cursor_col=self.cursor_col,
            )
            self.text_lines[self.cursor_row] = line[: self.cursor_col - 1] + line[self.cursor_col :]
            self.cursor_col -= 1
            return op
        prev_line = self.text_lines[self.cursor_row - 1]
        op = EditOp(
            kind="delete",
            row=self.cursor_row - 1,
            col=len(prev_line),
            text="\n",
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self.text_lines[self.cursor_row - 1] = prev_line + self.text_lines[self.cursor_row]
        self.text_lines.pop(self.cursor_row)
        self.cursor_row -= 1
        self.cursor_col = len(prev_line)
        return op

    def _undo(self) -> None:
        if not self.undo_stack:
            return
        op = self.undo_stack.pop()
        if op.kind == "insert":
            self._remove_text_at(op.row, op.col, op.text)
        else:
            self._insert_text_at(op.row, op.col, op.text)
        self.cursor_row = op.cursor_row
        self.cursor_col = op.cursor_col

    def _archive_session(self) -> None:
        text = self._current_text()
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        with self.sessions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _current_text(self) -> str:
        return "\n".join(self.text_lines).rstrip()

    def _clear_text(self) -> None:
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
            self.cursor_col = len(self.text_lines[self.cursor_row])

    def _move_cursor_right(self) -> None:
        line = self.text_lines[self.cursor_row]
        if self.cursor_col < len(line):
            self.cursor_col += 1
            return
        if self.cursor_row < len(self.text_lines) - 1:
            self.cursor_row += 1
            self.cursor_col = 0

    def _move_cursor_up(self) -> None:
        if self.cursor_row == 0:
            return
        self.cursor_row -= 1
        self.cursor_col = min(self.cursor_col, len(self.text_lines[self.cursor_row]))

    def _move_cursor_down(self) -> None:
        if self.cursor_row >= len(self.text_lines) - 1:
            return
        self.cursor_row += 1
        self.cursor_col = min(self.cursor_col, len(self.text_lines[self.cursor_row]))

    def _move_cursor_home(self) -> None:
        self.cursor_col = 0

    def _move_cursor_end(self) -> None:
        self.cursor_col = len(self.text_lines[self.cursor_row])

    def _move_cursor_page_up(self, lines: int) -> None:
        if self.cursor_row == 0:
            return
        self.cursor_row = max(0, self.cursor_row - lines)
        self.cursor_col = min(self.cursor_col, len(self.text_lines[self.cursor_row]))

    def _move_cursor_page_down(self, lines: int) -> None:
        if self.cursor_row >= len(self.text_lines) - 1:
            return
        self.cursor_row = min(len(self.text_lines) - 1, self.cursor_row + lines)
        self.cursor_col = min(self.cursor_col, len(self.text_lines[self.cursor_row]))

    def _text_to_lines(self, text: str) -> List[str]:
        lines = text.split("\n")
        return lines if lines else [""]

    def _open_recall(self) -> None:
        current = self._current_text()
        self.recall_items = [
            RecallSession(
                label="Current",
                text=current,
                preview=_preview_text(current),
                is_current=True,
            )
        ]
        for label, text in _load_recent_sessions(self.sessions_path):
            self.recall_items.append(
                RecallSession(
                    label=label,
                    text=text,
                    preview=_preview_text(text),
                )
            )
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
        self.text_lines = self._text_to_lines(item.text)
        self.undo_stack = []
        self.cursor_row = max(0, len(self.text_lines) - 1)
        self.cursor_col = len(self.text_lines[self.cursor_row]) if self.text_lines else 0
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
            if self.font.size(candidate)[0] <= max_width:
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
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.recall_strip_rect.collidepoint(event.pos):
                self.recall_open = False
                self.recall_drag_last_y = None
                self.recall_pressed_index = None
                self.recall_drag_distance = 0
                return
            self.recall_drag_last_y = event.pos[1]
            self.recall_pressed_index = self._recall_index_at_pos(event.pos)
            self.recall_drag_distance = 0
            return
        if event.type == pygame.MOUSEMOTION and self.recall_drag_last_y is not None:
            dy = event.pos[1] - self.recall_drag_last_y
            self._scroll_recall(-dy)
            self.recall_drag_distance += abs(dy)
            self.recall_drag_last_y = event.pos[1]
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if (
                self.recall_pressed_index is not None
                and self.recall_drag_distance < 10
                and self._recall_index_at_pos(event.pos) == self.recall_pressed_index
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

            label_surface = self.font.render(item.label, True, (30, 30, 30))
            self.screen.blit(label_surface, (rect.left + preview_x_pad, rect.top + preview_y_pad))

            preview_top = rect.top + preview_y_pad + self.font.get_height() + 6
            max_width = rect.width - preview_x_pad * 2
            available_height = rect.bottom - preview_top - preview_y_pad
            line_step = self.font.get_height() + 4
            max_lines = max(1, available_height // line_step)
            lines = self._wrap_preview_lines(item.preview, max_width, max_lines)
            for line_idx, line in enumerate(lines):
                y = preview_top + line_idx * line_step
                if y + self.font.get_height() > rect.bottom - preview_y_pad:
                    break
                line_surface = self.font.render(line, True, (40, 40, 40))
                self.screen.blit(line_surface, (rect.left + preview_x_pad, y))

    def _render(self) -> None:
        self.screen.fill((248, 248, 248))

        draw_home_button(self.screen, self.home_button.rect)
        self.recall_button.draw(self.screen, self.font)
        self.undo_button.draw(self.screen, self.font)
        self.new_button.draw(self.screen, self.font)

        y = self.margin + 60
        for line in self.text_lines:
            text_surface = self.font.render(line, True, (20, 20, 20))
            self.screen.blit(text_surface, (self.margin, y))
            y += self.font.get_height() + 6

        cursor_line = self.text_lines[self.cursor_row]
        cursor_x = self.margin + self.font.size(cursor_line[: self.cursor_col])[0]
        cursor_y = self.margin + 60 + self.cursor_row * (self.font.get_height() + 6)
        pygame.draw.rect(self.screen, (30, 30, 30), (cursor_x, cursor_y, 6, self.font.get_height()))

        if self.recall_open:
            self._draw_recall_overlay()

        pygame.display.flip()

    def run(self) -> None:
        running = True
        lines_per_page = max(1, (self.screen_rect.height - (self.margin + 80)) // (self.font.get_height() + 6))
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
                            self._move_cursor_page_up(lines_per_page)
                        elif event.key == pygame.K_PAGEDOWN:
                            self._move_cursor_page_down(lines_per_page)
                    elif event.key in {pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_LALT, pygame.K_RALT}:
                        continue
                    elif event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI):
                        continue
                    else:
                        if event.unicode and event.unicode.isprintable():
                            self._insert_char(event.unicode)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.home_button.hit(event.pos):
                        running = False
                    elif self.recall_button.hit(event.pos):
                        self._open_recall()
                    elif self.undo_button.hit(event.pos):
                        self._undo()
                    elif self.new_button.hit(event.pos):
                        self._archive_session()
                        self._clear_text()

            self._render()
            self.clock.tick(60)

        pygame.quit()


def main() -> None:
    try:
        TypingApp().run()
    except Exception:
        pygame.quit()


if __name__ == "__main__":
    main()
