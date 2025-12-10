# BrickBuilder

A Python-based 3D brick building application built with PySide6 and OpenGL.

## Features
- **3D Viewport**: Smooth 3D navigation with Orbit, Pan, and Zoom.
- **Brick Placement**: Intuitive snap-to-grid placement system.
- **Tools**:
  - **Place (Q)**: Add blocks. (Hold Ctrl to remove).
  - **Select (W)**: Select blocks to view details.
  - **Paint (E)**: Color blocks with a palette.
  - **Erase (R)**: Remove blocks.
- **Color Palette**: Choose from standard brick colors.
- **Save/Load**: Persist your creations to JSON files.

## Getting Started

### Prerequisites
- Python 3.13+
- [`uv`](https://github.com/astral-sh/uv) package manager

### Installation
1. Clone the repository.
2. Install dependencies:
   ```bash
   uv sync
   ```

### Running
Start the application:
```bash
uv run run_app.py
```

## Controls

### Camera
- **Orbit**: `Alt + Left Click` (or Middle Mouse)
- **Pan**: `Shift + Alt + Left Click` (or Shift + Middle Mouse)
- **Zoom**: `Scroll Wheel`

### General
- **Tools**: Keys `Q`, `W`, `E`, `R` to switch tools.
- **File**: `Ctrl+N` (New), `Ctrl+O` (Open), `Ctrl+S` (Save).
