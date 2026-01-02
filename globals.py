from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import MainWindow, TrayIcon

main_window: "MainWindow"
tray_icon: "TrayIcon"

def set_tooltip(message: str):
    """Set the tooltip of the tray icon"""
    tray_icon.state_update_callback(message)
