import sys
import os
import time
from PyQt6.QtWidgets import QApplication

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui import (
    APRILCore,
    APRILBridge,
    TransitionalOverlay,
)
import database

def main():
    print("Initializing Qt application for V4 UI capture (minimal)...")
    app = QApplication(sys.argv)
    
    database.init_db()
    
    core = APRILCore()
    bridge = APRILBridge(core)
    
    overlay = TransitionalOverlay(core)
    bridge.attach_overlay(overlay)
    
    print("Showing Layer 2 Quick Peek card...")
    overlay.show_peek("Note", "write unit tests for the bridge layer")
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()
    
    compact_path = "actual_compact_view.png"
    pixmap = overlay.grab()
    pixmap.save(compact_path)
    print(f"Quick Peek Card saved to {compact_path}")
    
    overlay.hide()
    app.processEvents()
    print("UI capture completed successfully!")
    sys.exit(0)

if __name__ == "__main__":
    main()
