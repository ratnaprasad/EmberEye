import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from main_window import BEMainWindow

"""Minimal automated test to exercise logout and ensure no QThread abort.
Runs the main window, triggers logout after 1s, then quits the app after 3s.
Observe exit code; expect 0 if threads shut down cleanly.
"""

def run_test():
    app = QApplication(sys.argv)
    win = BEMainWindow()
    win.show()
    # Trigger logout (which will close and reopen login window) then quit
    QTimer.singleShot(1000, win.logout)
    QTimer.singleShot(3000, app.quit)
    rc = app.exec_()
    print(f"Test logout exit code: {rc}")
    return rc

if __name__ == "__main__":
    sys.exit(run_test())
