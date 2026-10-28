"""Close the specific mini-program window only after a verified login response.

Uses WM_CLOSE, as the window's close button does; never terminates WeChat.
Win32 is loaded lazily. No desktop is touched on import or by the pure planner.
"""
import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass
from pathlib import PureWindowsPath
import time

WECHAT_PROCESSES = frozenset(('wechat.exe', 'weixin.exe', 'wechatappex.exe',
                              'weixinappex.exe', 'wechatapphost.exe', 'wmpf.exe'))
MAIN_TITLES = frozenset(('微信', 'wechat', 'weixin', '微信登录', '登录'))
MAIN_CLASSES = frozenset(('wechatmainwndforpc', 'wechatloginwndforpc'))


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    created: int
    executable: str
    class_name: str
    title: str
    visible: bool = True

    @property
    def process_name(self):
        return PureWindowsPath(self.executable).name.lower()

    @property
    def identity(self):
        return (self.hwnd, self.pid, self.created, self.executable.casefold(), self.class_name)


def eligible(window):
    return (window.visible and window.hwnd not in (0, 0xffff) and window.pid > 0 and window.created > 0
            and window.process_name in WECHAT_PROCESSES and bool(window.title.strip())
            and window.title.strip().casefold() not in MAIN_TITLES
            and window.class_name.casefold() not in MAIN_CLASSES)


def matches(window, values):
    if not eligible(window):
        return False
    title = values.get('wechat_window_title', '').strip()
    if title:
        return (window.title == title
                and window.class_name == values.get('wechat_window_class', '')
                and window.process_name == values.get('wechat_window_process', '').casefold())
    return '广东医缴费' in window.title


class WindowsDesktop:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wt.LPARAM]
        self.user.EnumWindows.restype = wt.BOOL
        for name in ('IsWindow', 'IsWindowVisible'):
            getattr(self.user, name).argtypes = [wt.HWND]
            getattr(self.user, name).restype = wt.BOOL
        self.user.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        self.user.GetWindowThreadProcessId.restype = wt.DWORD
        self.user.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        self.user.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        self.user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.user.PostMessageW.restype = wt.BOOL
        self.kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self.kernel.OpenProcess.restype = wt.HANDLE
        self.kernel.CloseHandle.argtypes = [wt.HANDLE]
        self.kernel.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wt.BOOL
        self.kernel.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wt.BOOL

    def get(self, hwnd):
        if not self.user.IsWindow(hwnd):
            return None
        pid = wt.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not process:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wt.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
                return None
            created, ended, kernel, user = (wt.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(process, *[ctypes.byref(x) for x in (created, ended, kernel, user)]):
                return None
            # Check again in case the original window disappeared during inspection.
            pid_again = wt.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_again))
            if pid_again.value != pid.value:
                return None
            title, klass = ctypes.create_unicode_buffer(4096), ctypes.create_unicode_buffer(512)
            self.user.GetWindowTextW(hwnd, title, len(title))
            self.user.GetClassNameW(hwnd, klass, len(klass))
            return Window(int(hwnd), pid.value, (created.dwHighDateTime << 32) | created.dwLowDateTime,
                          path.value, klass.value, title.value, bool(self.user.IsWindowVisible(hwnd)))
        finally:
            self.kernel.CloseHandle(process)

    def windows(self):
        result = []
        def visit(hwnd, unused):
            try:
                if self.user.IsWindowVisible(hwnd):
                    value = self.get(hwnd)
                    if value and eligible(value):
                        result.append(value)
            except OSError:
                pass
            return True
        callback = self.callback_type(visit)
        if not self.user.EnumWindows(callback, 0):
            raise OSError('无法读取微信窗口列表。')
        return result

    def close(self, snapshot):
        current = self.get(snapshot.hwnd)
        if current is None or current.identity != snapshot.identity or not eligible(current):
            return False
        if current.title != snapshot.title:
            return False
        if not self.user.PostMessageW(snapshot.hwnd, 0x0010, 0, 0):
            raise OSError('Windows 未接受窗口关闭请求，请检查微信与本软件是否以相同权限运行。')
        return True


class CloseAfterToken:
    def __init__(self, values, note, desktop=None, clock=time.monotonic):
        self.values, self.note, self.clock = values, note, clock
        self._desktop = desktop
        self.armed_until = 0
        self.target = None
        self.close_at = 0
        self.check_at = 0
        self.next_observation = 0
        self.selector = None

    @property
    def desktop(self):
        if self._desktop is None:
            self._desktop = WindowsDesktop()
        return self._desktop

    def cancel(self):
        self.armed_until = self.close_at = self.check_at = 0
        self.target = None
        self.selector = None

    def options_key(self):
        values = self.values()
        return tuple(values.get(key, '') for key in ('wechat_window_title', 'wechat_window_class', 'wechat_window_process'))

    def find(self):
        candidates = [item for item in self.desktop.windows() if matches(item, self.values())]
        return candidates[0] if len(candidates) == 1 else None

    def armed(self):
        """Only a shortcut invocation by this software starts a close cycle."""
        self.cancel()
        if not self.values().get('wechat_close_after_token', True):
            return
        self.selector = self.options_key()
        self.armed_until = self.clock() + 180
        self.target = self.find()  # Also handles a pre-existing window brought forward.
        self.next_observation = self.clock() + .5

    def validated(self):
        if (not self.values().get('wechat_close_after_token', True)
                or self.clock() > self.armed_until or self.selector != self.options_key()):
            self.cancel()
            return
        if self.target is None:
            self.target = self.find()
        if self.target is None:
            self.note('Token 已验证，但未唯一识别本轮小程序窗口；请在设置中选择目标窗口，或手动关闭。')
            self.cancel()
            return
        self.armed_until = 0
        self.close_at = self.clock() + 3
        self.note('Token 已验证，3 秒后关闭本次唤起的小程序窗口。')

    def poll(self):
        if not (self.armed_until or self.close_at or self.check_at):
            return
        if (not self.values().get('wechat_close_after_token', True)
                or self.selector != self.options_key()):
            self.cancel()
            return
        now = self.clock()
        if self.armed_until:
            if now > self.armed_until:
                self.cancel()
            elif self.target is None and now >= self.next_observation:
                self.next_observation = now + 1
                self.target = self.find()
        elif self.close_at and now >= self.close_at:
            self.close_at = 0
            current = self.desktop.get(self.target.hwnd)
            if current is None or not current.visible:
                self.note('本轮小程序窗口已关闭。')
                self.cancel()
            elif current.identity != self.target.identity or not matches(current, self.values()):
                self.note('目标窗口身份或页面标题已改变，已取消自动关闭。')
                self.cancel()
            elif self.desktop.close(self.target):
                self.check_at = now + 2
            else:
                self.note('目标窗口已变化，未发送关闭请求。')
                self.cancel()
        elif self.check_at and now >= self.check_at:
            current = self.desktop.get(self.target.hwnd)
            if current is None or current.identity != self.target.identity or not current.visible:
                self.note('已关闭本轮小程序窗口，下次唤起将重新打开。')
            else:
                self.note('已发送关闭请求，但小程序窗口仍存在；请手动关闭或处理窗口提示。')
            self.cancel()
