import sys
import traceback
from pathlib import Path

LOG_PATH = Path(__file__).with_name("_diag_widget_start.log")

def write(line: str) -> None:
    LOG_PATH.write_text(LOG_PATH.read_text(encoding="utf-8") + line + "\n", encoding="utf-8") if LOG_PATH.exists() else LOG_PATH.write_text(line + "\n", encoding="utf-8")

write("diag:start")
try:
    from PyQt6.QtWidgets import QApplication
    write("diag:qt_import_ok")
    app = QApplication(sys.argv[:1])
    write("diag:app_ok")
    from widget import APRILWidget
    write("diag:widget_import_ok")
    widget = APRILWidget({"voice": False, "at_home": True, "terminal_visible": True})
    write(f"diag:widget_construct_ok:{type(widget).__name__}")
    widget.destroy()
    app.quit()
    write("diag:done")
except Exception:
    write(traceback.format_exc())
    raise
