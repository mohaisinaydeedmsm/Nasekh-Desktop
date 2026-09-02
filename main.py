import sys
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal
from ui.main_window import MainWindow

class ExceptionRelay(QObject):
    error_signal = Signal(str, str)

def setup_exception_handling(window):
    relay = ExceptionRelay(window)
    relay.error_signal.connect(window.show_unhandled_error)

    def custom_excepthook(exctype, value, tb):
        err_msg = "".join(traceback.format_exception(exctype, value, tb))
        summary = f"{exctype.__name__}: {value}"
        print(f"\n[!] UNHANDLED EXCEPTION CAUGHT:\n{err_msg}", file=sys.stderr)
        relay.error_signal.emit(summary, err_msg)

    sys.excepthook = custom_excepthook

def main():
    app = QApplication(sys.argv)
    window = MainWindow()

    setup_exception_handling(window)

    if "--test" in sys.argv:
        print("[OK] MainWindow created and initialized successfully.")
        return 0

    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
