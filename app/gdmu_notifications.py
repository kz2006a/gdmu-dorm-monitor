"""Native Windows notification-area balloons. No PowerShell or SMTP dependency."""
import ctypes
from ctypes import wintypes as wt
import threading


class GUID(ctypes.Structure):
    _fields_=[('Data1',wt.DWORD),('Data2',wt.WORD),('Data3',wt.WORD),('Data4',ctypes.c_ubyte*8)]


class NotifyIconData(ctypes.Structure):
    _fields_=[('cbSize',wt.DWORD),('hWnd',wt.HWND),('uID',wt.UINT),('uFlags',wt.UINT),
              ('uCallbackMessage',wt.UINT),('hIcon',wt.HICON),('szTip',wt.WCHAR*128),
              ('dwState',wt.DWORD),('dwStateMask',wt.DWORD),('szInfo',wt.WCHAR*256),
              ('uVersion',wt.UINT),('szInfoTitle',wt.WCHAR*64),('dwInfoFlags',wt.DWORD),
              ('guidItem',GUID),('hBalloonIcon',wt.HICON)]


def short(value, units):
    return str(value).replace('\0',' ').encode('utf-16-le',errors='replace')[:units*2].decode('utf-16-le',errors='ignore')


def balance_notice(name,info,reasons,moment):
    def display(key):
        value=info.get(key)
        return '未提供' if value is None or value=='' else short(value,30)
    return '\n'.join((f'宿舍：{short(name,45)}',
                      f'电量：{display("electricityBalance")} 度  |  水量：{display("waterBalance")} 吨',
                      f'查询于 {moment:%m-%d %H:%M}（北京时间）',
                      '；'.join(reasons) if reasons else '以上为学校接口返回的余量。'))


class NativeNotifier:
    def __init__(self,root):
        self.root=root
        self.lock=threading.Lock()
        self.hwnd=None
        self.icon=None
        self.shell=None
        self.added=False
        self.closed=False

    def prepare(self):
        """Call on the Tk thread before a worker may submit notifications."""
        with self.lock:
            if self.closed:raise ValueError('通知服务已关闭。')
            if self.shell is not None:return
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.GetAncestor.argtypes=[wt.HWND,wt.UINT];user.GetAncestor.restype=wt.HWND
            user.LoadIconW.argtypes=[wt.HINSTANCE,wt.LPCWSTR];user.LoadIconW.restype=wt.HICON
            self.hwnd=user.GetAncestor(self.root.winfo_id(),2)
            self.icon=user.LoadIconW(None,ctypes.cast(ctypes.c_void_p(32516),wt.LPCWSTR))
            shell=ctypes.WinDLL('shell32',use_last_error=True)
            shell.Shell_NotifyIconW.argtypes=[wt.DWORD,ctypes.POINTER(NotifyIconData)]
            shell.Shell_NotifyIconW.restype=wt.BOOL
            if not self.hwnd or not self.icon:raise OSError('无法初始化 Windows 通知窗口。')
            self.shell=shell

    def data(self):
        data=NotifyIconData();data.cbSize=ctypes.sizeof(data)
        data.hWnd=self.hwnd;data.uID=1600;data.hIcon=self.icon
        data.szTip='广东医校园水电 · 监测通知'
        return data

    def show(self,title,body,warning=False):
        """Thread-safe after prepare; TRUE means accepted, not necessarily seen."""
        with self.lock:
            if self.closed or self.shell is None:return False
            data=self.data()
            if not self.added:
                data.uFlags=0x2|0x4
                if not self.shell.Shell_NotifyIconW(0,ctypes.byref(data)):return False
                self.added=True
                data.uVersion=4
                self.shell.Shell_NotifyIconW(4,ctypes.byref(data))
            data.uFlags=0x10|0x80
            data.szInfoTitle=short(title,63);data.szInfo=short(body,255)
            data.dwInfoFlags=(2 if warning else 1)|0x80  # Respect Windows quiet time.
            accepted=bool(self.shell.Shell_NotifyIconW(1,ctypes.byref(data)))
            if not accepted:
                self.added=False  # Explorer may have restarted; recreate next time.
            return accepted

    def close(self):
        with self.lock:
            self.closed=True
            if self.added and self.shell is not None:
                self.shell.Shell_NotifyIconW(2,ctypes.byref(self.data()))
            self.added=False
