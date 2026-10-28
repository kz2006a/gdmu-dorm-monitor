"""Small frozen launcher; business modules live in the adjacent app folder."""
import runtime_support
import ctypes
import hashlib
import importlib
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox

sys.dont_write_bytecode = True
BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
APP = BASE / 'app'
_mutex = None


def main():
    global _mutex
    if not all((APP / name).is_file() for name in (
        'gdmu_desktop.py', 'gdmu_balance.py', 'gdmu_reminders.py', 'gdmu_mail_ui.py', 'gdmu_config.py'
    )):
        root = tk.Tk(); root.withdraw()
        messagebox.showerror('发布文件不完整', '请完整解压发布包，保留 EXE 同级的 app 和 _internal 文件夹。')
        root.destroy()
        return 1
    sys.path.insert(0, str(APP))
    if '--self-test-report' in sys.argv:
        index = sys.argv.index('--self-test-report')
        return importlib.import_module('gdmu_selftest').run(sys.argv[index + 1])
    if sys.platform == 'win32':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        name = 'Local\\GDMUDormMonitor_' + hashlib.sha256(str(BASE).casefold().encode()).hexdigest()[:24]
        _mutex = kernel.CreateMutexW(None, False, name)
        if ctypes.get_last_error() == 183:
            root = tk.Tk(); root.withdraw()
            messagebox.showinfo('程序已运行', '当前程序文件夹已有一个实例在运行，请打开或还原原来的窗口。')
            root.destroy()
            return 0
    gui = importlib.import_module('gdmu_desktop')
    root = tk.Tk()
    gui.BalanceApp(root, config_dir=BASE)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
