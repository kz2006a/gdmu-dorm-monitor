"""Run the desktop application from a source checkout."""
from pathlib import Path
import sys
import tkinter as tk
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'app'))
from gdmu_desktop import BalanceApp
if __name__ == '__main__':
    root = tk.Tk()
    BalanceApp(root, config_dir=ROOT)
    root.mainloop()
