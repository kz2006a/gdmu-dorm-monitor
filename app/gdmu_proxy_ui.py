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
        self.status = tk.StringVar(self.root, value='内置同步未接入；无需安装或启动 Fiddler。')
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
        self.window_closer = CloseAfterToken(controller.values, self.note)
        self.start_timer = self.root.after(800, self.startup)

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
            return
        self.prepare(connect_after=True)

    def enable_route(self):
        self.service.connect()
        self.ctl.vars['token_sync_enabled'].set(True)
        self.ctl.sync_changed()
        self.ctl.token_inbox.pulse()
        self.note('内置同步已接入。请在微信小程序查询；出现新登录响应后会自动验证 Token。')

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
                self.note(value)
            elif action == '准备并接入':
                try:
                    self.enable_route()
                except (ValueError, OSError) as exc:
                    self.note(str(exc))
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
                self.cancel_wake()
                self.note('两次唤起后仍未收到可用 Token，请手动进入小程序查询或完成学校登录。')
            else:
                try:
                    self.wake()
                    self.wake_count += 1
                    self.wake_deadline = time.monotonic() + 90
                    self.note(f'已唤起小程序（第 {self.wake_count}/2 次），等待实际登录响应。')
                except (OSError, ValueError) as exc:
                    self.cancel_wake()
                    self.note(str(exc))

    def open(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.deiconify()
            self.dialog.lift()
            return
        win = tk.Toplevel(self.root)
        self.dialog = win
        win.title('内置 HTTPS 同步 · 无需 Fiddler')
        win.geometry(f'760x{max(600, min(780, self.root.winfo_screenheight()-100))}')
        win.minsize(700, 600)
        footer = ttk.Frame(win, padding=(20, 10))
        footer.pack(side='bottom', fill='x')
        ttk.Button(footer, text='保存上述设置', command=self.save).pack(side='right')
        pane = ttk.Frame(win)
        pane.pack(fill='both', expand=True)
        canvas = tk.Canvas(pane, highlightthickness=0, background='#f3f6fb')
        scroll = ttk.Scrollbar(pane, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=20)
        item = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        win.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units') if event.delta else None)
        ttk.Label(body, text='首次：准备引擎 → 安装证书 → 开启同步', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(body, text='引擎随软件附带，无需另装 Python、Fiddler 或 mitmproxy。', wraplength=680).pack(anchor='w', pady=8)
        row = ttk.Frame(body)
        row.pack(fill='x', pady=8)
        for title, command in [('准备内置引擎', self.prepare), ('安装 HTTPS 证书', self.install_certificate), ('开启同步', self.connect)]:
            ttk.Button(row, text=title, command=command).pack(side='left', padx=(0, 8))
        row = ttk.Frame(body)
        row.pack(fill='x', pady=8)
        for title, command in [('关闭接入', self.disconnect), ('恢复网络', self.recover), ('移除本软件证书', lambda: self.install_certificate(False))]:
            ttk.Button(row, text=title, command=command).pack(side='left', padx=(0, 8))
        ttk.Label(body, textvariable=self.status, wraplength=670, foreground='#2167e8').pack(anchor='w', pady=10)
        ttk.Separator(body).pack(fill='x', pady=10)
        ttk.Checkbutton(body, text='启动软件后自动开启内置同步（会接入当前用户系统代理）', variable=self.ctl.vars['proxy_auto_start']).pack(anchor='w', pady=5)
        ttk.Label(body, text='只有安装证书并勾选保存后才自动接入。检测到其他系统代理时暂停接入。', wraplength=670).pack(anchor='w')
        ttk.Checkbutton(body, text='Token 失效时通过快捷方式唤起广东医缴费', variable=self.ctl.vars['wechat_auto_wake']).pack(anchor='w', pady=(18, 5))
        row = ttk.Frame(body)
        row.pack(fill='x', pady=5)
        ttk.Entry(row, textvariable=self.ctl.vars['wechat_shortcut']).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='选择快捷方式', command=self.choose_shortcut).pack(side='left', padx=8)
        ttk.Button(row, text='测试唤起', command=self.test_wake).pack(side='left')
        ttk.Checkbutton(body, text='本软件唤起后，Token 验证成功 3 秒后自动关闭小程序窗口',
                        variable=self.ctl.vars['wechat_close_after_token'], command=self.close_option_changed).pack(anchor='w', pady=(10, 5))
        row = ttk.Frame(body)
        row.pack(fill='x', pady=5)
        ttk.Button(row, text='选择小程序窗口', command=self.choose_window).pack(side='left')
        ttk.Button(row, text='恢复自动识别', command=self.automatic_window).pack(side='left', padx=8)
        ttk.Label(body, text='默认识别标题中包含“广东医缴费”的唯一窗口；识别不到时，请先打开小程序，再选择窗口绑定。'
                  '只向本轮目标窗口发送关闭请求，不结束微信进程。无效 Token 不会触发关闭。', wraplength=670).pack(anchor='w', pady=5)
        ttk.Label(body, text='仅选择微信创建的目标小程序快捷方式。是否支持创建取决于微信版本；'
                  '打开后若未自动重新登录，仍需在小程序进入水电查询页。当前版本不自动识别或点击小程序页面。', wraplength=670).pack(anchor='w', pady=8)
        ttk.Label(body, text='运行时仅解密 pay.gdmu.edu.cn；只保存目标登录接口的临时响应，读取后删除。'
                  '其他域名经本地代理透传。不要分享 .env、data 或 token-sync。\n\n'
                  '首次接入后若没有新登录响应，可关闭小程序窗口后重新打开。微信可能需要重新建立代理连接。'
                  '本机真实微信兼容性需要首次运行验证；证书校验不会被关闭。', wraplength=670, foreground='#526581').pack(anchor='w', pady=10)

    def close(self):
        self.closing.set()
        self.window_closer.cancel()
        if self.start_timer is not None:
            self.root.after_cancel(self.start_timer)
        self.cancel_wake()
        return self.service.shutdown()
