"""GUI for opt-in embedded capture. OS changes happen through explicit controls."""
from pathlib import Path
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from gdmu_proxy import ProxyService, certificate_action, certificate_trusted, certificate_thumbprint
from gdmu_wechat_window import CloseAfterToken, eligible


class EmbeddedSyncUI:
    def __init__(self, controller):
        self.ctl = controller
        self.root = controller.root
        self.service = ProxyService(controller.directory)
        self.status = tk.StringVar(self.root, value='点击连接，按提示完成首次接入。')
        self.events = queue.Queue()
        self.dialog = None
        self.busy = False
        self.closing = threading.Event()
        self.last_error = ''
        self.wake_job = None
        self.wake_count = 0
        self.wake_deadline = 0
        self.expiry_seen = False
        self.last_route_check = 0
        self.login_requested = False
        self.login_automatic = False
        self.recovery_connect_attempted = False
        self.window_closer = CloseAfterToken(controller.values, self.note)
        self.start_timer = self.root.after(800, self.startup)

    def begin_login(self):
        """Prepare automatically, retaining explicit consent for OS changes."""
        if self.busy:
            return
        self.login_requested = True
        self.login_automatic = False
        if self.service.connected:
            self.open_login_window()
        else:
            self.worker('准备登录', self.service.prepare)

    def request_login(self):
        self.login_requested = True
        self.login_automatic = True
        if self.service.connected and self.ctl.vars['wechat_auto_wake'].get():
            if self.ctl.waiting_for_token:
                self.login_requested = False  # poll owns the two-attempt recovery cycle
            else:
                self.open_login_window(automatic=True)

    def recovery_unavailable(self):
        if not self.ctl.vars['token_sync_enabled'].get():
            return '未开启 Token 同步，无法自动获取新登录。'
        if not self.ctl.vars['wechat_auto_wake'].get():
            return '未开启登录过期时自动打开小程序。'
        raw = self.ctl.vars['wechat_shortcut'].get().strip()
        path = Path(raw)
        if not raw or path.suffix.lower() not in ('.lnk', '.url') or not path.is_file():
            return '小程序快捷方式缺失或不可用。'
        if not self.service.connected and not self.busy and not self.ctl.vars['proxy_auto_start'].get():
            return '同步未连接，且未允许自动连接微信。'
        return ''

    def advance_recovery(self):
        if self.ctl.recovery is None or self.service.connected or self.busy:
            return
        if self.start_timer is not None or self.recovery_connect_attempted:
            return
        self.recovery_connect_attempted = True
        if not self.ctl.vars['proxy_auto_start'].get():
            self.ctl.fail_recovery('同步接入未完成，无法自动更新。')
        elif not certificate_trusted(self.ctl.directory):
            self.ctl.fail_recovery('本目录证书未受信任，不能自动连接。')
        else:
            # Uses the saved opt-in; never installs certificates automatically.
            self.prepare(connect_after=True)

    def open_login_window(self, automatic=False):
        self.login_requested = False
        if automatic and not self.ctl.vars['wechat_auto_wake'].get():
            self.note('登录已过期，请在微信打开广东医缴费。')
            return
        if not self.ctl.vars['wechat_shortcut'].get().strip():
            self.note('同步已连接，请在微信打开广东医缴费完成登录。')
            return
        self.test_wake()

    def startup(self):
        self.start_timer = None
        try:
            result = self.service.recover()
            if result == 'changed-externally':
                self.note('发现旧代理记录，但设置已被外部修改；请先检查 Windows 代理。')
                return
            if result in ('restored', 'already-restored'):
                self.note('已恢复上次运行前的 Windows 代理设置。')
            if self.ctl.vars['proxy_auto_start'].get():
                if not certificate_trusted(self.ctl.directory):
                    self.note('未确认 HTTPS 证书受信任，内置同步未自动开启。')
                else:
                    self.prepare(connect_after=True)
        except (ValueError, OSError) as exc:
            self.note(str(exc))

    def note(self, text):
        self.status.set(text)
        self.ctl.log('内置同步：' + text)

    def worker(self, action, job):
        if self.busy:
            return
        self.busy = True
        self.note('正在' + action + '，请稍候。')
        def run():
            try:
                value = job()
                self.events.put(('ok', action, value))
            except Exception as exc:
                text = str(exc) if isinstance(exc, (ValueError, OSError)) else '操作未完成，请检查程序文件与权限。'
                self.events.put(('error', action, text))
            finally:
                if self.closing.is_set():
                    try:
                        self.service.shutdown()
                    except (OSError, ValueError):
                        pass
        threading.Thread(target=run, daemon=True).start()

    def prepare(self, connect_after=False):
        self.worker('准备并接入' if connect_after else '准备内置引擎', self.service.prepare)

    def connect(self):
        if self.busy:
            return
        if not certificate_trusted(self.ctl.directory):
            messagebox.showinfo('需要 HTTPS 证书', '请先准备引擎，再安装本目录专用证书。', parent=self.dialog or self.root)
            return
        if not messagebox.askokcancel('开启内置同步',
            '开启期间，Windows 当前用户的系统代理会指向本软件。\n\n'
            '使用该系统代理的应用流量会经过本地引擎；仅学校缴费域名进行 HTTPS 解密，'
            '其他域名透传。本软件只提取学校 code2Session 登录响应。\n\n'
            '关闭同步或退出时恢复原代理。请先关闭 Fiddler 或其他系统代理。', parent=self.dialog or self.root):
            self.login_requested = False
            self.note('已取消连接。')
            return
        self.prepare(connect_after=True)

    def enable_route(self):
        self.service.connect()
        self.ctl.vars['token_sync_enabled'].set(True)
        self.ctl.sync_changed()
        self.ctl.token_inbox.pulse()
        self.note('同步已连接，等待微信登录。')
        if self.login_requested:
            if self.login_automatic and self.ctl.waiting_for_token:
                self.login_requested = False
            else:
                self.open_login_window(automatic=self.login_automatic)
        elif not self.ctl.app.token.get().strip():
            self.open_login_window(automatic=True)

    def disconnect(self):
        if self.busy:
            self.note('当前操作尚未完成；完成后可关闭接入。')
            return
        try:
            result = self.service.disconnect()
            self.cancel_wake()
            self.window_closer.cancel()
            self.ctl.vars['proxy_auto_start'].set(False)
            self.ctl.save_settings(silent=True, validate_auto=False)
            self.note('代理已被外部修改，未覆盖外部设置；请检查 Windows 代理。' if result == 'changed-externally' else '已关闭接入并恢复原代理。')
        except (ValueError, OSError) as exc:
            self.note(str(exc))

    def recover(self):
        if self.busy:
            return
        try:
            result = self.service.recover()
            self.service.connected = False
            self.note('代理已被其他程序修改，保留其设置；如无法上网，请打开 Windows 设置检查。' if result == 'changed-externally' else '恢复检查完成，未遗留本软件的代理接入。')
        except (ValueError, OSError) as exc:
            self.note(str(exc))

    def install_certificate(self, install=True):
        if self.busy:
            return
        if not install and self.service.connected:
            messagebox.showinfo('请先关闭接入', '移除证书前，请先关闭内置代理接入。', parent=self.dialog or self.root)
            return
        try:
            thumb = certificate_thumbprint(self.ctl.directory)
        except (OSError, ValueError):
            messagebox.showinfo('先准备引擎', '准备引擎后才会生成本软件专用证书。', parent=self.dialog or self.root)
            return
        text = ('将本软件专用根证书安装到当前 Windows 用户的受信任根存储。\n'
                '这会使本地引擎能够解密学校缴费域名的 HTTPS，以读取登录响应。\n'
                '证书和私钥在 data/https-proxy，请勿分享该目录。\n\n'
                if install else '将移除由此程序目录安装的用户根证书。\n\n') + '证书指纹：\n' + thumb
        if messagebox.askokcancel('安装 HTTPS 证书' if install else '移除 HTTPS 证书', text, parent=self.dialog or self.root):
            self.worker('安装证书' if install else '移除证书', lambda: certificate_action(self.ctl.directory, install))
        elif self.login_requested:
            self.login_requested = False
            self.note('已取消连接。')

    def choose_shortcut(self):
        path = filedialog.askopenfilename(parent=self.dialog or self.root,
            title='选择微信为广东医缴费创建的桌面快捷方式', filetypes=[('快捷方式', '*.lnk *.url')])
        if path:
            self.ctl.vars['wechat_shortcut'].set(path)
            self.save()

    def wake(self):
        raw = self.ctl.vars['wechat_shortcut'].get().strip()
        path = Path(raw)
        if not raw or path.suffix.lower() not in ('.lnk', '.url') or not path.is_file():
            raise ValueError('请先选择微信为广东医缴费创建的 .lnk 或 .url 快捷方式。若当前微信不支持创建，请手动打开小程序。')
        try:
            self.window_closer.armed()
        except OSError:
            self.window_closer.cancel()
            self.note('无法识别小程序窗口，本轮只唤起，不自动关闭。')
        try:
            os.startfile(str(path.resolve()))
        except OSError:
            self.window_closer.cancel()
            raise

    def test_wake(self):
        try:
            self.wake()
            self.note('已打开所选快捷方式。只有收到并验证登录 Token 后，才会显示刷新成功。')
        except (OSError, ValueError) as exc:
            self.note(str(exc))

    def save(self):
        if self.ctl.vars['proxy_auto_start'].get() and not certificate_trusted(self.ctl.directory):
            messagebox.showinfo('证书未就绪', '先准备并安装证书，再保存启动后自动接入。', parent=self.dialog or self.root)
            self.ctl.vars['proxy_auto_start'].set(False)
        if self.ctl.save_settings(silent=True, validate_auto=False):
            self.note('内置同步设置已保存。')

    def cancel_wake(self):
        self.wake_deadline = 0
        self.wake_count = 0

    def validated(self):
        self.cancel_wake()
        self.expiry_seen = False
        try:
            self.window_closer.validated()
        except OSError:
            self.window_closer.cancel()
            self.note('Token 已接入，但读取目标窗口失败，请手动关闭小程序。')

    def close_option_changed(self):
        self.window_closer.cancel()
        self.ctl.save_settings(silent=True, validate_auto=False)

    def automatic_window(self):
        for key in ('wechat_window_title', 'wechat_window_class', 'wechat_window_process'):
            self.ctl.vars[key].set('')
        self.close_option_changed()
        self.note('恢复自动识别：仅匹配唯一的“广东医缴费”窗口。')

    def choose_window(self):
        win = tk.Toplevel(self.root)
        win.title('选择广东医缴费的小程序窗口')
        win.geometry('780x360')
        ttk.Label(win, text='先打开广东医缴费，再刷新列表并选择它的窗口。微信主窗口和登录窗口不会列出。', wraplength=740).pack(anchor='w', padx=16, pady=12)
        tree = ttk.Treeview(win, columns=('title', 'process', 'class'), show='headings', height=7)
        for key, title, width in (('title', '窗口标题', 300), ('process', '进程', 170), ('class', '窗口类', 230)):
            tree.heading(key, text=title)
            tree.column(key, width=width)
        tree.pack(fill='both', expand=True, padx=16)
        snapshots = {}
        def refresh():
            tree.delete(*tree.get_children())
            snapshots.clear()
            try:
                for item in self.window_closer.desktop.windows():
                    key = str(item.hwnd)
                    snapshots[key] = item
                    tree.insert('', 'end', iid=key, values=(item.title, item.process_name, item.class_name))
            except OSError as exc:
                messagebox.showerror('读取失败', str(exc), parent=win)
        def select():
            choice = tree.selection()
            if not choice:
                return
            old = snapshots[choice[0]]
            current = self.window_closer.desktop.get(old.hwnd)
            if current is None or current.identity != old.identity or current.title != old.title or not eligible(current):
                messagebox.showinfo('窗口已变化', '请刷新列表后重新选择。', parent=win)
                return
            self.ctl.vars['wechat_window_title'].set(current.title)
            self.ctl.vars['wechat_window_class'].set(current.class_name)
            self.ctl.vars['wechat_window_process'].set(current.process_name)
            self.close_option_changed()
            self.note('已绑定小程序窗口：' + current.title + '。下次唤起并验证 Token 后自动关闭。')
            win.destroy()
        actions = ttk.Frame(win, padding=12)
        actions.pack(fill='x')
        ttk.Button(actions, text='刷新窗口列表', command=refresh).pack(side='left')
        ttk.Button(actions, text='绑定所选窗口', command=select).pack(side='right')
        refresh()

    def poll(self):
        if self.closing.is_set():
            return
        try:
            self.window_closer.poll()
        except OSError:
            self.window_closer.cancel()
            self.note('自动关闭小程序失败，请手动关闭；Token 与监测不受影响。')
        while True:
            try:
                kind, action, value = self.events.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            if kind == 'error':
                self.login_requested = False
                self.note(value)
                self.ctl.fail_recovery('同步引擎操作失败：' + value)
            elif action == '准备登录':
                if certificate_trusted(self.ctl.directory):
                    self.connect()
                else:
                    self.install_certificate()
            elif action == '安装证书' and self.login_requested:
                self.connect()
            elif action == '准备并接入':
                try:
                    self.enable_route()
                except (ValueError, OSError) as exc:
                    self.note(str(exc))
                    self.ctl.fail_recovery('同步接入失败：' + str(exc))
            else:
                self.note(value or '内置引擎已就绪。首次使用请安装证书，然后开启同步。')
        if self.service.connected and not self.service.alive:
            try:
                result = self.service.shutdown()
                self.note('HTTPS 引擎意外停止，已恢复原代理。' if result != 'changed-externally' else 'HTTPS 引擎停止；代理已被外部修改，请检查网络。')
            except (ValueError, OSError) as exc:
                self.note(str(exc))
        if self.service.connected and time.monotonic() - self.last_route_check > 2:
            self.last_route_check = time.monotonic()
            try:
                from gdmu_proxy import load_lease
                lease = load_lease(self.service.lease)
                if lease is None or self.service.settings.read() != lease['expected']:
                    self.service.connected = False
                    self.cancel_wake()
                    self.note('系统代理已被其他程序更改；内置同步暂停接入，未覆盖外部设置。')
            except (ValueError, OSError) as exc:
                self.note(str(exc))
        self.advance_recovery()
        waiting = self.ctl.waiting_for_token and self.ctl.desired_running
        if not waiting:
            self.expiry_seen = False
            self.cancel_wake()
        elif (self.service.connected and self.ctl.vars['wechat_auto_wake'].get() and not self.expiry_seen):
            self.expiry_seen = True
            self.wake_count = 0
            self.wake_deadline = time.monotonic()
        if waiting and self.wake_deadline and time.monotonic() >= self.wake_deadline:
            if self.wake_count >= 2:
                if self.ctl.recovery is not None and (self.ctl.token_validation_busy or self.ctl.app.busy or self.ctl.preflight_busy):
                    self.wake_deadline = time.monotonic() + 1
                else:
                    self.cancel_wake()
                    self.note('两次唤起后仍未收到可用 Token，请手动进入小程序查询或完成学校登录。')
                    self.ctl.fail_recovery('两次自动唤起后，仍未收到并验证可用 Token。')
            else:
                try:
                    self.wake()
                    self.wake_count += 1
                    self.wake_deadline = time.monotonic() + 90
                    self.note(f'已唤起小程序（第 {self.wake_count}/2 次），等待实际登录响应。')
                except (OSError, ValueError) as exc:
                    self.cancel_wake()
                    self.note(str(exc))
                    self.ctl.fail_recovery('小程序自动打开失败：' + str(exc))

    def open(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.deiconify()
            self.dialog.lift()
            return
        from gdmu_ui import build_proxy_dialog
        build_proxy_dialog(self)

    def close(self):
        self.closing.set()
        self.window_closer.cancel()
        if self.start_timer is not None:
            self.root.after_cancel(self.start_timer)
        self.cancel_wake()
        return self.service.shutdown()
