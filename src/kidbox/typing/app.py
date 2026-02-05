from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

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
        self.new_button = Button(
            rect=pygame.Rect(self.screen_rect.width - button_w - 20, 20, button_w, button_h),
            label="New",
            fill=(240, 240, 240),
        )
        self.margin = 40

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
            text="\\n",
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
        text = "\n".join(self.text_lines).rstrip()
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        with self.sessions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

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

    def run(self) -> None:
        running = True
        lines_per_page = max(1, (self.screen_rect.height - (self.margin + 80)) // (self.font.get_height() + 6))
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
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
                    elif self.undo_button.hit(event.pos):
                        self._undo()
                    elif self.new_button.hit(event.pos):
                        self._archive_session()
                        self._clear_text()

            self.screen.fill((248, 248, 248))

            draw_home_button(self.screen, self.home_button.rect)
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

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


def main() -> None:
    try:
        TypingApp().run()
    except Exception:
        pygame.quit()


if __name__ == "__main__":
    main()
