r"""test_surface_only.py
Full main.py import chain, surface system only, no widget.py.
Run from the april directory with: .venv\Scripts\python.exe src/test_surface_only.py
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

def main():
    print("[test] importing runtime modules...")
    from debug_log import log_event
    from event_ledger import append_event
    from state_engine import refresh_state_snapshot

    print("[test] runtime modules OK")

    print("[test] creating QApplication...")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    print("[test] QApplication OK")

    print("[test] importing surface system...")
    from ui import (
        APRILCore,
        APRILBridge,
        AmbientAnchor,
        TransitionalOverlay,
        TacticalWorkspace,
        SettingsPanel,
    )

    print("[test] surface imports OK")

    print("[test] constructing surfaces...")
    core = APRILCore()
    bridge = APRILBridge(core)
    anchor = AmbientAnchor(core)
    overlay = TransitionalOverlay(core)
    workspace = TacticalWorkspace(core)
    settings = SettingsPanel(core)
    print("[test] surfaces constructed")

    bridge.attach_overlay(overlay)
    bridge.attach_workspace(workspace)
    core.settings_requested.connect(settings.show)
    print("[test] bridge wired")

    anchor.show()
    anchor._force_topmost()
    bridge.set_state("idle")
    print(
        f"[test] anchor shown — winId={int(anchor.winId())} pos={anchor.pos()} size={anchor.size()} visible={anchor.isVisible()}"
    )

    # Cycle states every 2s so animation changes are obvious
    import itertools

    _states = itertools.cycle(["listening", "thinking", "speaking", "idle"])

    def _next_state():
        s = next(_states)
        bridge.set_state(s)
        print(f"[test] state -> {s}")

    state_timer = QTimer()
    state_timer.setInterval(2000)
    state_timer.timeout.connect(_next_state)
    state_timer.start()

    QTimer.singleShot(12000, app.quit)
    print("[test] entering app.exec() — orb should be in bottom-right corner")
    app.exec()
    print("[test] done")

if __name__ == '__main__':
    main()
