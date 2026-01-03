import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MainWindow, TrayIcon

main_window: "MainWindow"
tray_icon: "TrayIcon"

repo_locks: dict[str, asyncio.Lock] = {}

def get_repo_lock(repo_url: str) -> asyncio.Lock:
    """Get or create an asyncio lock for a given repository URL"""
    if repo_url not in repo_locks:
        repo_locks[repo_url] = asyncio.Lock()
    return repo_locks[repo_url]

def set_tooltip(message: str):
    """Set the tooltip of the tray icon"""
    tray_icon.state_update_callback(message)
    main_window.setWindowTitle(f"ResticTray - {message}")
