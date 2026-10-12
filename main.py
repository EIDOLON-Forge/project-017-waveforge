
"""
EIDOLON — PROJECT #017
WAVEFORGE // AUDIO EDITION

Procedural tile-world generator with synthesized sound effects.

Requirements:
    Python 3.12+
    pygame 2.6.1

Run:
    python main.py

Controls:
    SPACE       Start / pause
    N           Single generation step
    R           Generate a new world
    C           Clear / reset
    E           Export JSON
    M           Toggle sound
    [ / ]       Lower / raise volume
    - / +       Slower / faster generation
    UP / DOWN   Change grid size
    1 / 2 / 3   Change palette
    G           Toggle grid lines
    L           Toggle tile labels
    ESC         Quit

Mouse:
    Left-click  Inspect a cell
    Right-click Restart generation
"""

from __future__ import annotations

import json
import math
import random
import struct
import sys
import time
from collections import deque
from pathlib import Path

import pygame


# ============================================================
# CONFIGURATION
# ============================================================

WIDTH, HEIGHT = 1280, 800
FPS = 60
SIDEBAR_W = 280
MARGIN = 24
HEADER_H = 88
FOOTER_H = 36

MIN_COLS, MAX_COLS = 12, 42
DEFAULT_COLS = 30
DEFAULT_ROWS = 22

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"

BG = (7, 11, 17)
PANEL = (13, 19, 28)
PANEL_ALT = (19, 28, 40)
BORDER = (39, 52, 69)
TEXT = (225, 236, 246)
MUTED = (122, 145, 166)
WHITE = (245, 249, 255)
GREEN = (91, 239, 179)
BLUE = (93, 178, 255)
ORANGE = (255, 182, 99)
RED = (255, 105, 125)

TILES = ("ground", "water", "forest", "wall", "path", "building")

WEIGHTS = {
    "ground": 42,
    "water": 12,
    "forest": 22,
    "wall": 8,
    "path": 11,
    "building": 5,
}

PALETTES = {
    "EIDOLON": {
        "ground": (29, 53, 51),
        "water": (29, 91, 132),
        "forest": (35, 111, 77),
        "wall": (75, 85, 105),
        "path": (151, 135, 99),
        "building": (112, 92, 139),
        "accent": (91, 239, 179),
        "background": (7, 11, 17),
    },
    "OCEAN": {
        "ground": (41, 78, 86),
        "water": (25, 100, 158),
        "forest": (35, 116, 112),
        "wall": (92, 112, 128),
        "path": (183, 166, 122),
        "building": (113, 105, 161),
        "accent": (80, 222, 235),
        "background": (5, 13, 22),
    },
    "EMBER": {
        "ground": (83, 58, 44),
        "water": (49, 89, 120),
        "forest": (49, 103, 65),
        "wall": (111, 92, 83),
        "path": (202, 143, 83),
        "building": (154, 76, 65),
        "accent": (255, 171, 92),
        "background": (16, 10, 10),
    },
}

RULES = {
    "ground": {
        d: set(TILES) for d in ("N", "E", "S", "W")
    },
    "water": {
        d: {"ground", "water", "forest"} for d in ("N", "E", "S", "W")
    },
    "forest": {
        d: {"ground", "water", "forest", "path"}
        for d in ("N", "E", "S", "W")
    },
    "wall": {
        d: {"ground", "wall", "building"}
        for d in ("N", "E", "S", "W")
    },
    "path": {
        d: {"ground", "forest", "path", "building"}
        for d in ("N", "E", "S", "W")
    },
    "building": {
        d: {"ground", "wall", "path", "building"}
        for d in ("N", "E", "S", "W")
    },
}

DIRECTIONS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}


# ============================================================
# HELPERS
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def mix_color(a, b, amount):
    amount = clamp(amount, 0.0, 1.0)
    return tuple(
        int(a[i] + (b[i] - a[i]) * amount)
        for i in range(3)
    )


def rounded(surface, color, rect, radius=9, width=0):
    pygame.draw.rect(
        surface, color, rect, width=width, border_radius=radius
    )


def text(surface, font, value, color, pos):
    image = font.render(str(value), True, color)
    surface.blit(image, pos)
    return image.get_rect(topleft=pos)


def centered_text(surface, font, value, color, center):
    image = font.render(str(value), True, color)
    surface.blit(image, image.get_rect(center=center))


# ============================================================
# SYNTHESIZED AUDIO ENGINE
# ============================================================

class AudioEngine:
    """
    Creates short sounds and ambient audio mathematically.
    No WAV or MP3 files are required.
    """

    SAMPLE_RATE = 22050

    def __init__(self):
        self.enabled = True
        self.volume = 0.42
        self.ambient_volume = 0.12
        self.sounds = {}
        self.ambient = None
        self.ambient_channel = None
        self.available = False

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(
                    frequency=self.SAMPLE_RATE,
                    size=-16,
                    channels=1,
                    buffer=512,
                )

            self.available = True
            self._build_sounds()
            self._build_ambient()
        except pygame.error as exc:
            print(f"Audio unavailable: {exc}")
            self.available = False

    def _make_tone(
        self,
        frequency=440,
        duration=0.10,
        volume=0.22,
        waveform="sine",
        end_frequency=None,
        noise=0.0,
    ):
        """Generate a mono, signed 16-bit sound buffer."""
        count = max(1, int(self.SAMPLE_RATE * duration))
        output = bytearray()

        end_frequency = (
            frequency if end_frequency is None else end_frequency
        )

        phase = 0.0

        for i in range(count):
            t = i / self.SAMPLE_RATE
            progress = i / max(1, count - 1)
            freq = frequency + (end_frequency - frequency) * progress
            phase += math.tau * freq / self.SAMPLE_RATE

            if waveform == "square":
                sample = 1.0 if math.sin(phase) >= 0 else -1.0
            elif waveform == "triangle":
                sample = (2.0 / math.pi) * math.asin(math.sin(phase))
            elif waveform == "soft":
                sample = (
                    math.sin(phase)
                    + 0.24 * math.sin(phase * 2.0)
                    + 0.08 * math.sin(phase * 3.0)
                ) / 1.32
            else:
                sample = math.sin(phase)

            if noise:
                sample += random.uniform(-1.0, 1.0) * noise

            attack = min(1.0, t / 0.012)
            release = min(1.0, (duration - t) / 0.035)
            envelope = max(0.0, min(attack, release))

            # Very short fade-in/out prevents sharp audio clicks.
            value = int(
                32767 * clamp(sample * volume * envelope, -1.0, 1.0)
            )
            output.extend(struct.pack("<h", value))

        return pygame.mixer.Sound(buffer=bytes(output))

    def _build_sounds(self):
        specs = {
            "tick": (720, 0.035, 0.11, "sine", 520, 0.0),
            "ground": (250, 0.045, 0.12, "soft", 205, 0.0),
            "water": (590, 0.10, 0.16, "sine", 930, 0.0),
            "forest": (390, 0.075, 0.13, "soft", 540, 0.0),
            "wall": (170, 0.08, 0.16, "triangle", 125, 0.0),
            "path": (460, 0.07, 0.13, "sine", 650, 0.0),
            "building": (310, 0.12, 0.16, "soft", 490, 0.0),
            "start": (330, 0.24, 0.22, "soft", 660, 0.0),
            "pause": (500, 0.12, 0.16, "sine", 320, 0.0),
            "complete": (440, 0.38, 0.18, "soft", 880, 0.0),
            "restart": (620, 0.14, 0.16, "triangle", 260, 0.0),
            "export": (760, 0.12, 0.16, "sine", 1020, 0.0),
            "conflict": (210, 0.17, 0.18, "triangle", 110, 0.0),
            "click": (680, 0.045, 0.12, "sine", 570, 0.0),
        }

        for name, spec in specs.items():
            freq, duration, volume, wave_type, end_freq, noise = spec
            self.sounds[name] = self._make_tone(
                freq,
                duration,
                volume,
                wave_type,
                end_freq,
                noise,
            )

    def _build_ambient(self):
        """Generate a quiet evolving drone for looping playback."""
        duration = 8.0
        count = int(self.SAMPLE_RATE * duration)
        output = bytearray()

        for i in range(count):
            t = i / self.SAMPLE_RATE

            # Slow oscillations create a subtle sci-fi atmosphere.
            drift = 0.5 + 0.5 * math.sin(math.tau * t / duration)
            tone = (
                0.44 * math.sin(math.tau * 55.0 * t)
                + 0.23 * math.sin(math.tau * 82.41 * t)
                + 0.15 * math.sin(math.tau * 110.0 * t)
                + 0.08 * math.sin(math.tau * 164.81 * t)
            )

            # Fade the beginning and end to soften the loop boundary.
            fade_in = min(1.0, t / 0.25)
            fade_out = min(1.0, (duration - t) / 0.25)
            envelope = max(0.0, min(fade_in, fade_out))
            sample = tone * (0.70 + 0.30 * drift) * envelope * 0.16

            output.extend(
                struct.pack(
                    "<h",
                    int(32767 * clamp(sample, -1.0, 1.0)),
                )
            )

        self.ambient = pygame.mixer.Sound(buffer=bytes(output))
        self.ambient.set_volume(self.ambient_volume)

    def play(self, name, volume_scale=1.0):
        if not self.available or not self.enabled:
            return

        sound = self.sounds.get(name)
        if sound is None:
            return

        sound.set_volume(clamp(self.volume * volume_scale, 0.0, 1.0))
        sound.play()

    def tile_sound(self, tile):
        mapping = {
            "ground": "ground",
            "water": "water",
            "forest": "forest",
            "wall": "wall",
            "path": "path",
            "building": "building",
        }
        self.play(mapping.get(tile, "tick"), 0.70)

    def start_ambient(self):
        if not self.available or not self.enabled or self.ambient is None:
            return

        if self.ambient_channel is None or not self.ambient_channel.get_busy():
            self.ambient_channel = self.ambient.play(-1)

        if self.ambient_channel:
            self.ambient_channel.set_volume(self.ambient_volume)

    def stop_ambient(self):
        if self.ambient_channel:
            self.ambient_channel.fadeout(250)
            self.ambient_channel = None

    def toggle(self):
        self.enabled = not self.enabled

        if self.enabled:
            self.play("click")
        else:
            self.stop_ambient()

        return self.enabled

    def adjust_volume(self, delta):
        self.volume = clamp(self.volume + delta, 0.0, 1.0)
        self.ambient_volume = self.volume * 0.28

        if self.ambient:
            self.ambient.set_volume(self.ambient_volume)

        if self.ambient_channel:
            self.ambient_channel.set_volume(self.ambient_volume)

    def close(self):
        self.stop_ambient()


# ============================================================
# CELL MODEL
# ============================================================

class Cell:
    def __init__(self):
        self.options = set(TILES)
        self.collapsed = False

    @property
    def tile(self):
        if self.collapsed and len(self.options) == 1:
            return next(iter(self.options))
        return None


# ============================================================
# PROCEDURAL GENERATOR
# ============================================================

class WaveForge:
    def __init__(self, cols, rows, seed=None):
        self.cols = cols
        self.rows = rows
        self.seed = seed if seed is not None else random.randrange(1, 2**31)
        self.rng = random.Random(self.seed)
        self.reset(self.seed)

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed

        self.rng = random.Random(self.seed)
        self.cells = [
            Cell() for _ in range(self.cols * self.rows)
        ]

        self.running = False
        self.complete = False
        self.failed = False
        self.steps = 0
        self.collapses = 0
        self.propagations = 0
        self.restarts = 0
        self.started_at = None
        self.finished_at = None
        self.recent_cell = None
        self.recent_cells = set()
        self.last_tile = None
        self.last_error = ""

    def index(self, x, y):
        return y * self.cols + x

    def in_bounds(self, x, y):
        return 0 <= x < self.cols and 0 <= y < self.rows

    def cell_at(self, x, y):
        return self.cells[self.index(x, y)] if self.in_bounds(x, y) else None

    def neighbors(self, x, y):
        for direction, (dx, dy) in DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                yield direction, nx, ny, self.cell_at(nx, ny)

    def unresolved(self):
        return sum(not cell.collapsed for cell in self.cells)

    def progress(self):
        return 1.0 - self.unresolved() / max(1, len(self.cells))

    def elapsed(self):
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.perf_counter()
        return max(0.0, end - self.started_at)

    def start(self):
        if self.complete or self.failed:
            return
        self.running = True
        if self.started_at is None:
            self.started_at = time.perf_counter()

    def pause(self):
        self.running = False

    def choose_cell(self):
        candidates = [
            (i, cell)
            for i, cell in enumerate(self.cells)
            if not cell.collapsed and cell.options
        ]

        if not candidates:
            return None

        minimum = min(len(cell.options) for _, cell in candidates)
        tied = [
            pair for pair in candidates
            if len(pair[1].options) == minimum
        ]
        return self.rng.choice(tied)

    def propagate(self, start_x, start_y):
        queue = deque([(start_x, start_y)])
        queued = {(start_x, start_y)}
        self.recent_cells.clear()

        while queue:
            x, y = queue.popleft()
            queued.discard((x, y))
            current = self.cell_at(x, y)

            if current is None:
                continue

            self.recent_cells.add((x, y))

            for direction, nx, ny, neighbor in self.neighbors(x, y):
                permitted = set()

                for possible_tile in current.options:
                    permitted.update(RULES[possible_tile][direction])

                revised = neighbor.options & permitted

                if revised != neighbor.options:
                    neighbor.options = revised
                    self.propagations += 1

                    if not revised:
                        return False

                    if len(revised) == 1:
                        neighbor.collapsed = True

                    if (nx, ny) not in queued:
                        queue.append((nx, ny))
                        queued.add((nx, ny))

        return True

    def recover(self):
        self.restarts += 1
        self.last_error = "Constraint conflict — restarting"

        if self.restarts >= 12:
            self.failed = True
            self.running = False
            self.finished_at = time.perf_counter()
            self.last_error = "Recovery limit reached. Press R to retry."
            return

        # Keep the recovery counter across reset.
        count = self.restarts
        new_seed = self.rng.randrange(1, 2**31)
        self.reset(new_seed)
        self.restarts = count
        self.last_error = "Recovered from constraint conflict"

    def step(self):
        if self.complete or self.failed:
            self.running = False
            return None

        choice = self.choose_cell()

        if choice is None:
            if all(
                cell.collapsed and len(cell.options) == 1
                for cell in self.cells
            ):
                self.complete = True
                self.running = False
                self.finished_at = time.perf_counter()
            else:
                self.recover()
            return None

        index, cell = choice
        x, y = index % self.cols, index // self.cols

        tile = self.rng.choices(
            list(cell.options),
            weights=[WEIGHTS[t] for t in cell.options],
            k=1,
        )[0]

        cell.options = {tile}
        cell.collapsed = True
        self.steps += 1
        self.collapses += 1
        self.last_tile = tile
        self.recent_cell = (x, y)

        if not self.propagate(x, y):
            self.recover()
            return None

        if all(
            c.collapsed and len(c.options) == 1
            for c in self.cells
        ):
            self.complete = True
            self.running = False
            self.finished_at = time.perf_counter()

        return tile

    def export(self, path=None):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        if path is None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = EXPORT_DIR / f"waveforge-{stamp}.json"

        grid = []
        for y in range(self.rows):
            row = []
            for x in range(self.cols):
                cell = self.cell_at(x, y)
                row.append(cell.tile or "unresolved")
            grid.append(row)

        data = {
            "project": "EIDOLON #017",
            "name": "WAVEFORGE",
            "seed": self.seed,
            "width": self.cols,
            "height": self.rows,
            "complete": self.complete,
            "steps": self.steps,
            "elapsed_seconds": round(self.elapsed(), 3),
            "grid": grid,
        }

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path


# ============================================================
# APPLICATION
# ============================================================

class App:
    def __init__(self):
        pygame.mixer.pre_init(
            frequency=AudioEngine.SAMPLE_RATE,
            size=-16,
            channels=1,
            buffer=512,
        )
        pygame.init()

        pygame.display.set_caption("EIDOLON #017 — WAVEFORGE")
        self.screen = pygame.display.set_mode(
            (WIDTH, HEIGHT), pygame.RESIZABLE
        )
        self.clock = pygame.time.Clock()

        self.font_tiny = pygame.font.SysFont("consolas", 12)
        self.font_small = pygame.font.SysFont("consolas", 13)
        self.font_body = pygame.font.SysFont("consolas", 15)
        self.font_medium = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_title = pygame.font.SysFont("consolas", 28, bold=True)

        self.cols, self.rows = DEFAULT_COLS, DEFAULT_ROWS
        self.solver = WaveForge(self.cols, self.rows)

        self.palette_name = "EIDOLON"
        self.palette = PALETTES[self.palette_name]
        self.audio = AudioEngine()

        self.steps_per_frame = 2
        self.show_grid = True
        self.show_labels = False
        self.selected = None
        self.toast = ""
        self.toast_until = 0
        self.running = True

        self.resize_layout()

    def resize_layout(self):
        self.width, self.height = self.screen.get_size()
        self.width = max(800, self.width)
        self.height = max(600, self.height)

        self.play_area = pygame.Rect(
            MARGIN,
            HEADER_H,
            self.width - SIDEBAR_W - MARGIN * 3,
            self.height - HEADER_H - FOOTER_H - MARGIN,
        )

        self.sidebar = pygame.Rect(
            self.width - SIDEBAR_W - MARGIN,
            HEADER_H,
            SIDEBAR_W,
            self.height - HEADER_H - FOOTER_H - MARGIN,
        )

        self.cell_size = max(
            8,
            min(
                self.play_area.width // self.cols,
                self.play_area.height // self.rows,
            ),
        )

        grid_w = self.cell_size * self.cols
        grid_h = self.cell_size * self.rows
        self.grid_rect = pygame.Rect(
            self.play_area.x + (self.play_area.width - grid_w) // 2,
            self.play_area.y + (self.play_area.height - grid_h) // 2,
            grid_w,
            grid_h,
        )

    def notify(self, message, duration=2.0):
        self.toast = message
        self.toast_until = time.perf_counter() + duration

    def new_world(self, seed=None, play_sound=True):
        if seed is None:
            seed = random.randrange(1, 2**31)

        self.solver = WaveForge(self.cols, self.rows, seed)
        self.selected = None

        if play_sound:
            self.audio.play("restart")

        self.notify(f"World initialized · seed {seed}")

    def set_palette(self, name):
        if name in PALETTES:
            self.palette_name = name
            self.palette = PALETTES[name]
            self.audio.play("click")
            self.notify(f"Palette · {name}")

    def change_grid(self, delta):
        self.cols = int(clamp(self.cols + delta, MIN_COLS, MAX_COLS))
        self.rows = int(clamp(round(self.cols * 0.73), MIN_COLS, MAX_COLS))
        self.new_world()
        self.resize_layout()

    def export(self):
        try:
            path = self.solver.export()
            self.audio.play("export")
            self.notify(f"Exported · {path.name}")
        except OSError as exc:
            self.notify(f"Export failed · {exc}")

    def keydown(self, event):
        key = event.key

        if key == pygame.K_ESCAPE:
            self.running = False

        elif key == pygame.K_SPACE:
            if self.solver.running:
                self.solver.pause()
                self.audio.stop_ambient()
                self.audio.play("pause")
                self.notify("Generation paused")
            else:
                if self.solver.complete or self.solver.failed:
                    self.new_world(play_sound=False)
                self.solver.start()
                self.audio.play("start")
                self.audio.start_ambient()
                self.notify("Generation running")

        elif key == pygame.K_n:
            if not self.solver.complete and not self.solver.failed:
                self.solver.step()
                if self.solver.last_tile:
                    self.audio.tile_sound(self.solver.last_tile)
                self.notify("Single step", 0.8)

        elif key == pygame.K_r:
            self.new_world()

        elif key == pygame.K_c:
            self.solver.reset(self.solver.seed)
            self.selected = None
            self.audio.play("restart")
            self.notify("World cleared")

        elif key == pygame.K_e:
            self.export()

        elif key == pygame.K_m:
            enabled = self.audio.toggle()
            self.notify("Audio enabled" if enabled else "Audio muted")

        
        elif key == pygame.K_LEFTBRACKET:
            self.audio.adjust_volume(-0.05)
            self.notify(
                f"Volume · {int(self.audio.volume * 100)}%", 0.8
            )

        elif key == pygame.K_RIGHTBRACKET:
            self.audio.adjust_volume(0.05)
            self.notify(
                f"Volume · {int(self.audio.volume * 100)}%", 0.8
            )

        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.steps_per_frame = max(
                1, self.steps_per_frame - 1
            )
            self.notify(
                f"Speed · {self.steps_per_frame} steps/frame", 0.8
            )

        elif key in (
            pygame.K_PLUS,
            pygame.K_EQUALS,
            pygame.K_KP_PLUS,
        ):
            self.steps_per_frame = min(
                40, self.steps_per_frame + 1
            )
            self.notify(
                f"Speed · {self.steps_per_frame} steps/frame", 0.8
            )


        elif key in (pygame.K_RIGHTBRACKET, pygame.K_PLUS,
                     pygame.K_EQUALS, pygame.K_KP_PLUS):
            if key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.steps_per_frame = min(40, self.steps_per_frame + 1)
                self.notify(f"Speed · {self.steps_per_frame} steps/frame", 0.8)
            else:
                self.audio.adjust_volume(0.05)
                self.notify(f"Volume · {int(self.audio.volume * 100)}%", 0.8)

        elif key == pygame.K_UP:
            self.change_grid(2)

        elif key == pygame.K_DOWN:
            self.change_grid(-2)

        elif key == pygame.K_1:
            self.set_palette("EIDOLON")

        elif key == pygame.K_2:
            self.set_palette("OCEAN")

        elif key == pygame.K_3:
            self.set_palette("EMBER")

        elif key == pygame.K_g:
            self.show_grid = not self.show_grid

        elif key == pygame.K_l:
            self.show_labels = not self.show_labels

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False

        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode(
                event.size, pygame.RESIZABLE
            )
            self.resize_layout()

        elif event.type == pygame.KEYDOWN:
            self.keydown(event)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.grid_rect.collidepoint(event.pos):
                x = (event.pos[0] - self.grid_rect.x) // self.cell_size
                y = (event.pos[1] - self.grid_rect.y) // self.cell_size

                if self.solver.in_bounds(x, y):
                    self.selected = (int(x), int(y))
                    cell = self.solver.cell_at(int(x), int(y))
                    self.audio.play("click")
                    self.notify(
                        f"Cell ({x}, {y}) · "
                        f"{cell.tile or str(len(cell.options)) + ' options'}",
                        1.3,
                    )

            elif event.button == 3:
                self.new_world()
                self.solver.start()
                self.audio.start_ambient()
                self.audio.play("start")

    # --------------------------------------------------------
    # DRAWING
    # --------------------------------------------------------

    def draw_background(self):
        self.screen.fill(self.palette["background"])

        for x in range(0, self.width, 40):
            pygame.draw.line(
                self.screen, (12, 21, 30), (x, 0), (x, self.height)
            )

        for y in range(0, self.height, 40):
            pygame.draw.line(
                self.screen, (12, 21, 30), (0, y), (self.width, y)
            )

    def draw_header(self):
        accent = self.palette["accent"]

        text(
            self.screen, self.font_small,
            "E I D O L O N  /  PROCEDURAL SYSTEMS",
            MUTED, (MARGIN, 13),
        )
        text(
            self.screen, self.font_title,
            "WAVEFORGE", TEXT, (MARGIN, 31),
        )
        text(
            self.screen, self.font_small,
            "PROJECT #017  ·  AUDIO EDITION",
            accent, (MARGIN + 208, 44),
        )

        if self.solver.complete:
            state, state_color = "COMPLETE", GREEN
        elif self.solver.failed:
            state, state_color = "CONFLICT", RED
        elif self.solver.running:
            state, state_color = "RUNNING", BLUE
        else:
            state, state_color = "READY", ORANGE

        if not self.audio.enabled:
            state += " · MUTED"

        rect = pygame.Rect(self.width - 174, 31, 146, 34)
        rounded(self.screen, PANEL_ALT, rect, 8)
        rounded(self.screen, state_color, rect, 8, 1)
        centered_text(
            self.screen, self.font_small, state, state_color, rect.center
        )

        pygame.draw.line(
            self.screen, BORDER,
            (MARGIN, HEADER_H - 1),
            (self.width - MARGIN, HEADER_H - 1),
        )

    def draw_tile_detail(self, tile, rect):
        cx, cy = rect.center
        size = rect.width

        if tile == "water":
            col = mix_color(self.palette["water"], WHITE, 0.32)
            for offset in (-0.18, 0.0, 0.18):
                yy = int(cy + offset * size)
                pygame.draw.arc(
                    self.screen, col,
                    pygame.Rect(
                        rect.x + size * 0.18,
                        yy - size * 0.08,
                        size * 0.64,
                        size * 0.16,
                    ),
                    math.pi, math.tau, 1,
                )

        elif tile == "forest":
            col = mix_color(self.palette["forest"], WHITE, 0.26)
            radius = max(2, size // 7)
            for dx, dy in ((-0.15, 0.0), (0.12, -0.12), (0.1, 0.16)):
                pygame.draw.circle(
                    self.screen, col,
                    (int(cx + dx * size), int(cy + dy * size)),
                    radius,
                )

        elif tile == "wall":
            col = mix_color(self.palette["wall"], WHITE, 0.28)
            pygame.draw.line(
                self.screen, col,
                (rect.x + size * 0.2, cy),
                (rect.right - size * 0.2, cy), 1,
            )
            pygame.draw.line(
                self.screen, col,
                (cx, rect.y + size * 0.2),
                (cx, rect.bottom - size * 0.2), 1,
            )

        elif tile == "path":
            pygame.draw.circle(
                self.screen,
                mix_color(self.palette["path"], WHITE, 0.3),
                (cx, cy),
                max(1, size // 10),
            )

        elif tile == "building":
            inset = max(3, size // 4)
            inner = rect.inflate(-inset * 2, -inset * 2)
            pygame.draw.rect(
                self.screen,
                mix_color(self.palette["building"], WHITE, 0.3),
                inner, 1,
            )

    def draw_grid(self):
        size = self.cell_size
        gap = 1 if self.show_grid else 0

        rounded(self.screen, (4, 7, 11), self.grid_rect.inflate(8, 8), 5)

        for y in range(self.rows):
            for x in range(self.cols):
                cell = self.solver.cell_at(x, y)
                rect = pygame.Rect(
                    self.grid_rect.x + x * size,
                    self.grid_rect.y + y * size,
                    size - gap,
                    size - gap,
                )

                tile = cell.tile
                if tile:
                    color = self.palette[tile]
                else:
                    fraction = len(cell.options) / len(TILES)
                    color = mix_color(
                        (18, 26, 38), (46, 76, 86), 1.0 - fraction
                    )

                pygame.draw.rect(self.screen, color, rect)

                if tile:
                    self.draw_tile_detail(tile, rect)
                elif size >= 20:
                    # Tiny dots hint at the number of possibilities.
                    dot_count = min(5, len(cell.options))
                    for j in range(dot_count):
                        px = rect.x + 4 + j * 3
                        pygame.draw.circle(
                            self.screen, (112, 146, 160),
                            (px, rect.centery), 1,
                        )

                if self.show_labels and tile and size >= 20:
                    centered_text(
                        self.screen, self.font_tiny,
                        tile[0].upper(), WHITE, rect.center,
                    )

        for x, y in self.solver.recent_cells:
            rect = pygame.Rect(
                self.grid_rect.x + x * size,
                self.grid_rect.y + y * size,
                size - gap, size - gap,
            )
            pygame.draw.rect(
                self.screen, mix_color(GREEN, WHITE, 0.45), rect, 1
            )

        if self.solver.recent_cell:
            x, y = self.solver.recent_cell
            rect = pygame.Rect(
                self.grid_rect.x + x * size,
                self.grid_rect.y + y * size,
                size - gap, size - gap,
            )
            pygame.draw.rect(self.screen, WHITE, rect, 2)

        if self.selected:
            x, y = self.selected
            rect = pygame.Rect(
                self.grid_rect.x + x * size,
                self.grid_rect.y + y * size,
                size - gap, size - gap,
            )
            pygame.draw.rect(self.screen, ORANGE, rect, 2)

        pygame.draw.rect(self.screen, BORDER, self.grid_rect, 1)

    def card(self, y, title, height):
        rect = pygame.Rect(
            self.sidebar.x + 8, y,
            self.sidebar.width - 16, height,
        )
        rounded(self.screen, PANEL, rect, 9)
        rounded(self.screen, BORDER, rect, 9, 1)
        text(
            self.screen, self.font_tiny,
            title.upper(), MUTED, (rect.x + 12, rect.y + 9),
        )
        return rect

    def stat(self, label, value, x, y, color=TEXT):
        text(self.screen, self.font_tiny, label, MUTED, (x, y))
        text(self.screen, self.font_medium, value, color, (x, y + 16))

    def draw_sidebar(self):
        rounded(self.screen, PANEL, self.sidebar, 12)
        rounded(self.screen, BORDER, self.sidebar, 12, 1)

        px, py = self.sidebar.x, self.sidebar.y
        text(
            self.screen, self.font_medium,
            "SYSTEM TELEMETRY", TEXT, (px + 14, py + 12),
        )
        text(
            self.screen, self.font_tiny,
            "WORLD SEED", MUTED, (px + 14, py + 41),
        )
        text(
            self.screen, self.font_body,
            self.solver.seed, self.palette["accent"], (px + 14, py + 57),
        )

        card = self.card(py + 84, "Generation", 103)
        self.stat(
            "RESOLVED", f"{self.solver.progress() * 100:.1f}%",
            card.x + 12, card.y + 32, GREEN,
        )
        self.stat(
            "REMAINING", self.solver.unresolved(),
            card.x + 137, card.y + 32,
        )

        bar = pygame.Rect(card.x + 12, card.bottom - 17, card.width - 24, 5)
        rounded(self.screen, (34, 44, 57), bar, 3)
        fill = bar.copy()
        fill.width = int(bar.width * self.solver.progress())
        if fill.width:
            rounded(self.screen, self.palette["accent"], fill, 3)

        card = self.card(card.bottom + 9, "Algorithm", 88)
        self.stat(
            "COLLAPSES", self.solver.collapses,
            card.x + 12, card.y + 32, BLUE,
        )
        self.stat(
            "PROPAGATIONS", self.solver.propagations,
            card.x + 135, card.y + 32, ORANGE,
        )

        card = self.card(card.bottom + 9, "Performance", 82)
        self.stat(
            "ELAPSED", f"{self.solver.elapsed():.1f}s",
            card.x + 12, card.y + 31,
        )
        self.stat(
            "SPEED", f"{self.steps_per_frame}/frame",
            card.x + 135, card.y + 31,
        )

        card = self.card(card.bottom + 9, "Tile distribution", 143)
        counts = {tile: 0 for tile in TILES}
        for cell in self.solver.cells:
            if cell.tile:
                counts[cell.tile] += 1

        total = max(1, sum(counts.values()))
        row_y = card.y + 30
        for tile in TILES:
            count = counts[tile]
            fraction = count / total

            text(
                self.screen, self.font_tiny,
                tile.upper(), MUTED, (card.x + 12, row_y),
            )

            bar = pygame.Rect(card.x + 88, row_y + 2, 92, 7)
            rounded(self.screen, (32, 43, 55), bar, 3)

            fill = bar.copy()
            fill.width = int(bar.width * fraction)
            if fill.width:
                rounded(self.screen, self.palette[tile], fill, 3)

            text(
                self.screen, self.font_tiny,
                count, TEXT, (card.right - 33, row_y - 3),
            )
            row_y += 17

        card = self.card(card.bottom + 9, "Audio", 86)
        audio_state = "ON" if self.audio.enabled else "MUTED"
        audio_color = GREEN if self.audio.enabled else RED

        text(
            self.screen, self.font_body,
            f"STATUS  {audio_state}", audio_color,
            (card.x + 12, card.y + 31),
        )
        text(
            self.screen, self.font_tiny,
            f"VOLUME  {int(self.audio.volume * 100)}%",
            MUTED, (card.x + 12, card.y + 56),
        )

        # A tiny volume meter.
        meter = pygame.Rect(card.x + 133, card.y + 59, 80, 5)
        rounded(self.screen, (35, 46, 58), meter, 3)
        fill = meter.copy()
        fill.width = int(meter.width * self.audio.volume)
        if fill.width:
            rounded(self.screen, audio_color, fill, 3)

    def draw_footer(self):
        y = self.height - FOOTER_H

        pygame.draw.line(
            self.screen, BORDER,
            (MARGIN, y), (self.width - MARGIN, y),
        )

        left = "SPACE Start/Pause  N Step  R Restart  E Export  M Sound"
        right = "1/2/3 Palette  +/- Speed  [/] Volume"

        text(
            self.screen, self.font_tiny,
            left, MUTED, (MARGIN, y + 11),
        )

        image = self.font_tiny.render(right, True, MUTED)
        self.screen.blit(
            image,
            (self.width - MARGIN - image.get_width(), y + 11),
        )

    def draw_toast(self):
        if not self.toast or time.perf_counter() > self.toast_until:
            return

        image = self.font_body.render(self.toast, True, TEXT)
        rect = image.get_rect(
            center=(self.width // 2, self.height - FOOTER_H - 25)
        )
        rect.inflate_ip(26, 16)

        rounded(self.screen, PANEL_ALT, rect, 8)
        rounded(self.screen, self.palette["accent"], rect, 8, 1)
        self.screen.blit(image, image.get_rect(center=rect.center))

    def draw(self):
        self.draw_background()
        self.draw_header()
        self.draw_grid()
        self.draw_sidebar()
        self.draw_footer()
        self.draw_toast()
        pygame.display.flip()

    # --------------------------------------------------------
    # UPDATE AND MAIN LOOP
    # --------------------------------------------------------

    def update(self):
        if not self.solver.running:
            return

        for _ in range(self.steps_per_frame):
            if not self.solver.running:
                break

            was_complete = self.solver.complete
            was_failed = self.solver.failed
            tile = self.solver.step()

            if tile:
                # Avoid overwhelming the audio device at high speeds.
                if random.random() < 0.28:
                    self.audio.tile_sound(tile)

            if self.solver.complete and not was_complete:
                self.audio.stop_ambient()
                self.audio.play("complete")
                self.notify("World generation complete", 3.0)

            if self.solver.failed and not was_failed:
                self.audio.stop_ambient()
                self.audio.play("conflict")
                self.notify(self.solver.last_error, 3.0)

    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)

            self.update()
            self.draw()
            self.clock.tick(FPS)

        self.audio.close()
        pygame.quit()


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    try:
        App().run()
    except KeyboardInterrupt:
        pygame.quit()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
