
# EIDOLON #017 — WAVEFORGE

**A procedural tile-world generator built with Python and Pygame.**

WAVEFORGE is an interactive visualization of constraint-based procedural generation. It selects a cell with few remaining possibilities, chooses a tile, and propagates the resulting constraints to neighboring cells.

## Features

- Animated procedural tile generation
- Entropy-inspired cell selection
- Neighbor compatibility rules
- Six tile types: ground, water, forest, wall, path, and building
- Three visual palettes
- Live progress and tile-distribution statistics
- Step-by-step generation
- Adjustable generation speed
- Adjustable grid size
- Cell inspection
- JSON world export
- Contradiction recovery
- Dark EIDOLON-style interface

## Requirements

- Python 3.12 or compatible Python 3 version
- Pygame 2.6.1

## Installation

Create and enter the project directory, then run:

```bash
python -m venv .venv
```

On Windows Git Bash:

```bash
source .venv/Scripts/activate
```

Install the dependency:

```bash
python -m pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Controls

| Key | Action |
|---|---|
| `SPACE` | Start or pause generation |
| `N` | Execute one generation step |
| `R` | Restart with a new seed |
| `C` | Clear the world |
| `E` | Export the current map as JSON |
| `+` / `-` | Increase or decrease speed |
| `1` | EIDOLON palette |
| `2` | OCEAN palette |
| `3` | EMBER palette |
| `UP` | Increase grid size |
| `DOWN` | Decrease grid size |
| `G` | Toggle grid lines |
| `L` | Toggle tile labels |
| `ESC` | Quit |

**Mouse**
- Left-click a cell to inspect its coordinates and tile state.
- Right-click to restart generation.

## Exporting a World

Press `E`. The application creates an `exports/` directory and saves the current grid as a JSON file containing the seed, grid dimensions, progress metadata, and tile layout.

Cells that have not been resolved are marked `"unresolved"` in the export.

## How It Works

1. Each cell begins with a set of possible tile types.
2. The solver selects an unresolved cell with the fewest remaining possibilities.
3. It selects a tile using weighted random choice.
4. The selected tile constrains the possible tiles in neighboring cells.
5. Constraint changes propagate through the grid using a queue.
6. The process continues until the grid is resolved or a contradiction requires recovery.

This is an educational Wave Function Collapse-inspired solver. It demonstrates constraint propagation and entropy-inspired selection, rather than implementing the full original algorithm with a persistent decision stack and true backtracking.

## Smoke Test

Run:

```bash
python main.py --smoke-test
```

This runs a small solver test without opening the graphical application.

## Project Structure

```text
project-017-waveforge/
├── main.py
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Learning Outcomes

- Constraint satisfaction
- Grid-based algorithms
- Entropy-inspired heuristics
- Queue-based propagation
- Weighted random selection
- Procedural generation
- Pygame rendering and UI design
- JSON serialization

## License

MIT License. See `LICENSE`.

---

Built as part of the EIDOLON project series.
