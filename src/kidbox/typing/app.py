from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pygame

from kidbox.config import load_config
from kidbox.paths import ensure_directories, get_data_root
from kidbox.ui.common import Button, create_fullscreen_window, draw_home_button


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
        self.undo_stack: List[str] = []

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

    def _append_char(self, char: str) -> None:
        if char == "\n":
            self.text_lines.append("")
        else:
            self.text_lines[-1] += char
        self.undo_stack.append(char)
        if len(self.undo_stack) > 20:
            self.undo_stack.pop(0)

    def _remove_last_char(self) -> str | None:
        if len(self.text_lines) == 1 and self.text_lines[0] == "":
            return None
        if self.text_lines[-1]:
            removed = self.text_lines[-1][-1]
            self.text_lines[-1] = self.text_lines[-1][:-1]
            return removed
        else:
            if len(self.text_lines) > 1:
                self.text_lines.pop()
                return "\n"
        return None

    def _undo(self) -> None:
        if not self.undo_stack:
            return
        self.undo_stack.pop()
        self._remove_last_char()

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

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_BACKSPACE:
                        removed = self._remove_last_char()
                        if removed and self.undo_stack and self.undo_stack[-1] == removed:
                            self.undo_stack.pop()
                    elif event.key == pygame.K_RETURN:
                        self._append_char("\n")
                    elif event.key in {pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_LALT, pygame.K_RALT}:
                        continue
                    elif event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META | pygame.KMOD_GUI):
                        continue
                    else:
                        if event.unicode and event.unicode.isprintable():
                            self._append_char(event.unicode)
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

            last_line = self.text_lines[-1]
            cursor_x = self.margin + self.font.size(last_line)[0]
            cursor_y = self.margin + 60 + (len(self.text_lines) - 1) * (self.font.get_height() + 6)
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
