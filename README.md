# ResticTray

A Qt/PySide6 system tray icon application for Python.

## Features

- System tray icon integration
- Context menu with actions
- Notification support
- Double-click to show notifications

## Requirements

- Python 3.8+
- PySide6

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for fast Python package management.

```bash
# Install dependencies
uv sync
```

## Running the Application

```bash
# Run with uv
uv run main.py

# Or activate the virtual environment and run
source .venv/bin/activate  # On Linux/macOS
# .venv\Scripts\activate  # On Windows
python main.py
```

## Usage

Once running, the application will minimize to the system tray. You can:

- **Right-click** the tray icon to access the menu
- **Double-click** the tray icon to show a notification
- Select **Show Message** from the menu to display a notification
- Select **Quit** from the menu to exit the application

## Development

The project structure:

```
ResticTray/
├── main.py           # Main application file with tray icon implementation
├── pyproject.toml    # Project configuration and dependencies
├── uv.lock          # Locked dependencies
└── README.md        # This file
```

## License

MIT
