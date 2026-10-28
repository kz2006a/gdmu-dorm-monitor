"""Mail settings window and bridge between the UI and reminder worker."""
from datetime import datetime
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import gdmu_reminders as reminders
from gdmu_config import ConfigStore
from gdmu_token_sync import TokenInbox, fingerprint, fiddler_script, guard_candidate

DEFAULTS = {
    'host': '', 'port': '465', 'security': 'SSL/TLS', 'username': '',
    'sender': '', 'recipients': '', 'daily_enabled': False,
    'daily_times': '08:00, 20:00', 'threshold_enabled': True,
    'electricity_limit': '20', 'water_limit': '1',
    'interval_minutes': '30', 'repeat_hours': '24',
    'remember_credentials': True, 'auto_start': False,
    'token_sync_enabled': False,
}


class ReminderController:
    def __init__(self, app, backend, config_dir=None, auto_start=True):
        self.app, self.root, self.backend = app, app.root, backend
        self.store = ConfigStore(config_dir)
        self.directory = self.store.directory
        self.config_error = ''
        try:
            loaded = self.store.load()
        except (OSError, ValueError) as exc:
            self.config_error = str(exc) if isinstance(exc, ValueError) else '无法读取软件目录中的 .env 配置文件。'
            loaded = {'options': {}, 'token': '', 'password': '', 'target': {}}
        saved = loaded['options']
        self.vars = {}
        for key, default in DEFAULTS.items():
            value = saved.get(key, default)
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(self.root, value=value if isinstance(value, bool) else default)
            else:
                self.vars[key] = tk.StringVar(self.root, value=str(value))
        self.password = tk.StringVar(self.root, value=loaded['password'])
        if loaded['token']:
            self.app.token.set(loaded['token'])
        target = loaded['target']
        self.app.building_id.set(target.get('building', '9552'))
        self.app.room_id.set(target.get('room', '9632'))
        self.saved_target = dict(target)
        if target.get('name'):
            self.app.result_room.set('上次宿舍：' + target['name'])
        self.events = queue.Queue()
        self.monitor = None
        self.generation = 0
        self.dialog = None
        self.settings_widgets = []
        self.log_widget = None
        self.logs = []
        self.test_busy = False
        self.desired_running = False
        self.pending_retarget = False
        self.preflight_busy = False
        self.validation_cancel = threading.Event()
        self.waiting_for_token = False
        self.expired_intent = False
        self.token_validation_busy = False
        self.token_sync_epoch = 0
        self.pending_token_resume = False
        self.token_inbox = TokenInbox(self.directory, self.sync_note)
        self.last_sync_error = ''
        self.auto_timer = None
        self.poll_timer = self.root.after(250, self.poll)
        if self.config_error:
            self.app.reminder_status.set('配置读取失败：' + self.config_error)
            self.log(self.config_error + ' 请修正 .env 或在窗口中重新保存配置。')
        elif auto_start and self.vars['auto_start'].get():
            self.auto_timer = self.root.after(500, self.startup)
        self.app.sync_status.set('等待 Fiddler 登录响应；需先生成并安装同步片段。' if self.vars['token_sync_enabled'].get() else '未启用自动同步。新 Token 由微信小程序登录后产生。')

    @property
    def active(self):
        return self.monitor is not None and not self.monitor.stop_event.is_set()

    @property
    def startup_pending(self):
        return self.auto_timer is not None

    def cancel_startup(self):
        if self.auto_timer is not None:
            self.root.after_cancel(self.auto_timer)
            self.auto_timer = None

    def startup(self):
        self.auto_timer = None
        self.start(automatic=True)

    def values(self):
        return {key: variable.get() for key, variable in self.vars.items()}

    def save_settings(self, silent=False, validate_auto=True):
        try:
            values = self.values()
            if validate_auto and values['auto_start']:
                if not values['remember_credentials']:
                    raise ValueError('启动后自动提醒需要勾选保存 Token 和 SMTP 授权码。')
                if not self.app.token.get().strip():
                    raise ValueError('请先填写 Token，再保存自动提醒设置。')
                reminders.SMTPConfig.from_values(values, self.password.get())
                reminders.Rules.from_values(values)
            try:
                building, room, name = self.target()
                target = {'building': building, 'room': room, 'name': name}
            except ValueError:
                if validate_auto:
                    raise
                target = self.saved_target
            self.store.save(values, self.app.token.get().strip(), self.password.get(), target)
            self.saved_target = dict(target)
            self.config_error = ''
        except (OSError, ValueError) as exc:
            text = str(exc) if isinstance(exc, ValueError) else '无法写入软件目录的 .env，请把整个程序文件夹放到可写位置。'
            if not silent:
                messagebox.showerror('保存失败', text, parent=self.dialog or self.root)
            self.log('配置保存失败：' + text)
            return False
        if not silent:
            self.log('设置已保存到软件目录的 .env。' + ('已保存 Token 和 SMTP 授权码。' if values['remember_credentials'] else '未保存凭证，并已清除文件中的旧凭证。'))
        return True

    def sync_note(self, text):
        self.app.sync_status.set(text)
        self.log('Token 同步：' + text)

    def sync_changed(self):
        self.token_sync_epoch += 1
        self.token_validation_busy = False
        if self.vars['token_sync_enabled'].get():
            if self.expired_intent:
                self.waiting_for_token = True
                self.desired_running = True
            self.sync_note('已启用本地监听，请确认 Fiddler 已安装同步片段。')
        else:
            self.token_inbox.close()
            if self.waiting_for_token:
                self.stop('已关闭 Token 同步，提醒保持暂停。')
            self.sync_note('已关闭同步，不再接收登录响应。')
        self.save_settings(silent=True, validate_auto=False)

    def generate_sync_script(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / 'Fiddler_同步片段.txt'
            path.write_text(fiddler_script(self.directory), encoding='utf-8-sig')
            self.vars['token_sync_enabled'].set(True)
            self.sync_changed()
            self.token_inbox.pulse()
            os.startfile(str(path))
            messagebox.showinfo('接入片段已生成', '在 Fiddler Classic 中打开 Rules → Customize Rules，找到 OnBeforeResponse 函数。\n\n将刚生成的片段粘贴到该函数的大括号内，保留原有代码，保存后在小程序查询一次。\n\n移动软件文件夹后，请重新生成并更新片段路径。', parent=self.dialog or self.root)
        except OSError:
            messagebox.showerror('生成失败', '请检查软件目录是否可写；也可查看软件目录中的 Fiddler 接入说明。', parent=self.dialog or self.root)

    def show_sync_help(self):
        try:
            os.startfile(str(self.directory / 'Fiddler接入说明.md'))
        except OSError:
            messagebox.showinfo('Token 同步', '生成片段后，将其放入 Fiddler 的 OnBeforeResponse 函数内。保持软件和 Fiddler 运行，再在微信小程序查询，以捕获新的 code2Session 响应。', parent=self.root)

    def pump_token_sync(self):
        if not self.vars['token_sync_enabled'].get():
            return
        try:
            self.token_inbox.pulse()
            self.token_inbox.collect()
            self.last_sync_error = ''
            if self.token_validation_busy or self.preflight_busy or self.app.busy or self.pending_retarget:
                return
            candidate = self.token_inbox.take()
            if candidate is not None:
                self.begin_token_update(candidate)
        except OSError:
            if not self.last_sync_error:
                self.sync_note('同步目录不可读写，请检查软件目录权限。')
            self.last_sync_error = 'io'

    def begin_token_update(self, candidate):
        original = self.app.token.get().strip()
        if candidate == original and self.active:
            self.sync_note('响应中的 Token 已在当前监测中使用，无需替换。')
            return
        try:
            guard_candidate(original, candidate)
            building, room, name = self.target()
        except ValueError as exc:
            self.sync_note(str(exc))
            return
        self.token_validation_busy = True
        epoch = self.token_sync_epoch
        self.sync_note('正在验证候选 Token（指纹 ' + fingerprint(candidate) + '）。')
        def validate():
            try:
                self.backend.query_balance(candidate, building, room)
                self.events.put((epoch, 'sync_valid', (original, candidate)))
            except Exception as exc:
                self.events.put((epoch, 'sync_error', reminders.error_text(exc)))
        threading.Thread(target=validate, daemon=True).start()

    def apply_synced_token(self, original, candidate):
        if not self.vars['token_sync_enabled'].get():
            return
        if self.app.token.get().strip() != original:
            self.sync_note('校验期间 Token 已手动更改，已忽略较早的候选结果。')
            return
        want_resume = self.active or self.desired_running or self.waiting_for_token
        self.cancel_startup()
        self.validation_cancel.set()
        self.generation += 1
        if self.monitor is not None:
            self.monitor.stop()
        self.preflight_busy = False
        self.pending_retarget = False
        self.waiting_for_token = False
        self.expired_intent = False
        self.desired_running = want_resume
        self.app.token.set(candidate)
        self.app.last_token_value = candidate
        saved = self.save_settings(silent=True, validate_auto=False)
        text = '新 Token 已通过余量查询验证并接入（指纹 ' + fingerprint(candidate) + '）。'
        if not saved:
            text += ' 配置未能保存，当前仅在内存中使用。'
        self.sync_note(text)
        self.lock_settings(False)
        self.pending_token_resume = want_resume
        if not want_resume:
            self.app.reminder_status.set('Token 已更新；提醒仍保持手动停止状态。')

    def log(self, text):
        self.logs.append(f'{reminders.now_local():%H:%M:%S}  {text}')
        self.logs = self.logs[-60:]
        if self.log_widget is not None and self.log_widget.winfo_exists():
            self.log_widget.configure(state='normal')
            self.log_widget.delete('1.0', 'end')
            self.log_widget.insert('end', '\n'.join(self.logs))
            self.log_widget.see('end')
            self.log_widget.configure(state='disabled')

    def open(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.deiconify()
            self.dialog.lift()
            return
        win = tk.Toplevel(self.root)
        self.dialog = win
        self.settings_widgets = []
        win.title('邮件与提醒设置 · 广东医宿舍水电')
        win.geometry('790x780')
        win.minsize(700, 600)
        win.configure(bg='#f3f6fb')
        win.protocol('WM_DELETE_WINDOW', self.close_dialog)
        top = tk.Frame(win, bg='#152b4b', padx=24, pady=15)
        top.pack(fill='x')
        tk.Label(top, text='邮件与提醒设置', font=('Microsoft YaHei UI', 19, 'bold'), fg='white', bg='#152b4b').pack(anchor='w')
        tk.Label(top, text='可同时开启每日定时提醒和低余量提醒。', fg='#c4d3e9', bg='#152b4b', font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(5, 0))
        actions = tk.Frame(win, bg='#e8eef7', padx=18, pady=10)
        actions.pack(side='bottom', fill='x')
        ttk.Button(actions, text='保存设置', command=self.save_settings).pack(side='left')
        self.test_button = ttk.Button(actions, text='发送测试邮件', command=self.test_email)
        self.test_button.pack(side='left', padx=8)
        ttk.Button(actions, text='停止提醒', command=self.stop).pack(side='right')
        ttk.Button(actions, text='开始提醒', style='Primary.TButton', command=self.start).pack(side='right', padx=8)
        pane = tk.Frame(win, bg='#f3f6fb')
        pane.pack(fill='both', expand=True)
        canvas = tk.Canvas(pane, bg='#f3f6fb', highlightthickness=0)
        scrollbar = ttk.Scrollbar(pane, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(canvas, bg='#f3f6fb', padx=22, pady=16)
        item = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        win.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
                 if event.delta and not isinstance(event.widget, ttk.Combobox) else None)

        smtp = ttk.LabelFrame(body, text='SMTP 邮件服务', padding=14)
        smtp.pack(fill='x')
        smtp.columnconfigure(1, weight=1)
        for row, (title, key) in enumerate((
            ('SMTP 服务器', 'host'), ('端口', 'port'), ('连接加密', 'security'),
            ('登录账号', 'username'), ('密码 / 授权码', 'password'),
            ('发件人邮箱', 'sender'), ('收件人邮箱', 'recipients'),
        )):
            ttk.Label(smtp, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            if key == 'security':
                field = ttk.Combobox(smtp, textvariable=self.vars[key], values=('SSL/TLS', 'STARTTLS'), state='readonly')
                field.bind('<<ComboboxSelected>>', self.security_changed)
            else:
                field = ttk.Entry(smtp, textvariable=self.password if key == 'password' else self.vars[key],
                                  show='●' if key == 'password' else '')
            field.grid(row=row, column=1, sticky='ew', pady=4)
            self.settings_widgets.append(field)
        ttk.Label(smtp, text='发件人留空时使用登录账号；多个收件人用逗号分隔。', foreground='#728096', wraplength=590).grid(row=7, column=0, columnspan=2, sticky='w', pady=(8, 0))
        ttk.Label(smtp, text='请填写邮箱服务商提供的 SMTP 参数；授权码可能不同于网页登录密码。\n常见端口：SSL/TLS 465，STARTTLS 587，以服务商说明为准。', foreground='#728096', wraplength=600).grid(row=8, column=0, columnspan=2, sticky='w', pady=(5, 0))
        ttk.Label(smtp, text='设置保存在软件文件夹的 .env。勾选保存凭证后，该文件包含 Token 和授权码，请勿分享。', foreground='#728096', wraplength=600).grid(row=9, column=0, columnspan=2, sticky='w', pady=(5, 0))
        prefs = ttk.LabelFrame(body, text='重启与配置保存', padding=14)
        prefs.pack(fill='x', pady=(14, 0))
        ttk.Checkbutton(prefs, text='将 Token 和 SMTP 密码 / 授权码保存到当前目录 .env',
                        variable=self.vars['remember_credentials'], command=self.remember_changed).pack(anchor='w')
        ttk.Checkbutton(prefs, text='启动软件后自动开始提醒（先校验 Token 和 SMTP 登录）',
                        variable=self.vars['auto_start']).pack(anchor='w', pady=(8, 0))
        ttk.Label(prefs, text='保存设置、开始提醒或退出软件时写入配置；校验失败会暂停并显示原因。\n此选项用于启动本软件后的自动提醒，不会设置 Windows 开机启动。', foreground='#728096', wraplength=610).pack(anchor='w', pady=(8, 0))
        ttk.Button(prefs, text='打开配置所在文件夹', command=self.open_directory).pack(anchor='w', pady=(8, 0))
        ttk.Checkbutton(prefs, text='启用 Fiddler 登录响应 Token 自动同步',
                        variable=self.vars['token_sync_enabled'], command=self.sync_changed).pack(anchor='w', pady=(10, 0))
        ttk.Label(prefs, text='需一次性安装生成的 Fiddler 片段。只接收 code2Session 响应中的 Token；不会自行触发微信登录。', foreground='#728096', wraplength=610).pack(anchor='w', pady=(4, 0))

        rules = ttk.LabelFrame(body, text='提醒规则', padding=14)
        rules.pack(fill='x', pady=(14, 0))
        rules.columnconfigure(1, weight=1)
        daily = ttk.Checkbutton(rules, text='每天固定时间发送余量邮件', variable=self.vars['daily_enabled'])
        daily.grid(row=0, column=0, columnspan=2, sticky='w')
        self.settings_widgets.append(daily)
        self.rule_field(rules, 1, '北京时间 HH:MM', 'daily_times')
        ttk.Label(rules, text='可填写多个时间，如 08:00, 20:00。', foreground='#728096').grid(row=2, column=1, sticky='w')
        low = ttk.Checkbutton(rules, text='低余量时发送提醒（任一项满足即触发）', variable=self.vars['threshold_enabled'])
        low.grid(row=3, column=0, columnspan=2, sticky='w', pady=(12, 3))
        self.settings_widgets.append(low)
        self.rule_field(rules, 4, '电量 ≤（度）', 'electricity_limit')
        self.rule_field(rules, 5, '水量 ≤（吨）', 'water_limit')
        ttk.Label(rules, text='阈值留空表示不监测该项；零余量也会正常判断。', foreground='#728096').grid(row=6, column=0, columnspan=2, sticky='w', pady=4)
        self.rule_field(rules, 7, '查询间隔（分钟）', 'interval_minutes')
        self.rule_field(rules, 8, '持续不足重复提醒（小时）', 'repeat_hours')
        ttk.Label(rules, text='首次低于阈值时提醒；持续不足按上述间隔再次提醒。充值恢复后重新触发。', foreground='#728096', wraplength=610).grid(row=9, column=0, columnspan=2, sticky='w', pady=(8, 0))
        ttk.Label(rules, text='监测中切换宿舍会先暂停，选好新房间后自动校验并继续，无需重启软件。\n程序关闭、电脑关机或休眠期间无法执行查询和发送。最小化窗口可继续运行。', foreground='#526581', wraplength=610).grid(row=10, column=0, columnspan=2, sticky='w', pady=(8, 0))

        logbox = ttk.LabelFrame(body, text='运行记录', padding=10)
        logbox.pack(fill='x', pady=(14, 0))
        self.log_widget = tk.Text(logbox, height=7, wrap='word', font=('Microsoft YaHei UI', 9), relief='flat')
        self.log_widget.pack(fill='x')
        self.log_widget.insert('end', '\n'.join(self.logs) or '尚未启动提醒。可先发送测试邮件，验证 SMTP 配置。')
        self.log_widget.configure(state='disabled')
        self.lock_settings(self.active or self.preflight_busy)
        self.test_button.configure(state='disabled' if self.test_busy else 'normal')

    def rule_field(self, parent, row, title, key):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        field = ttk.Entry(parent, textvariable=self.vars[key])
        field.grid(row=row, column=1, sticky='ew', pady=4)
        self.settings_widgets.append(field)

    def remember_changed(self):
        if not self.vars['remember_credentials'].get():
            self.vars['auto_start'].set(False)

    def open_directory(self):
        try:
            os.startfile(str(self.directory))
        except OSError:
            messagebox.showerror('无法打开', '请手动打开 EXE 所在的程序文件夹。', parent=self.dialog or self.root)

    def security_changed(self, event=None):
        current = self.vars['port'].get()
        if current in ('465', '587'):
            self.vars['port'].set('465' if self.vars['security'].get() == 'SSL/TLS' else '587')

    def lock_settings(self, locked):
        for widget in self.settings_widgets:
            if widget.winfo_exists():
                widget.configure(state='disabled' if locked else 'readonly' if isinstance(widget, ttk.Combobox) else 'normal')

    def test_email(self):
        if self.test_busy:
            return
        try:
            config = reminders.SMTPConfig.from_values(self.values(), self.password.get())
        except ValueError as exc:
            messagebox.showinfo('请检查 SMTP 设置', str(exc), parent=self.dialog or self.root)
            return
        self.test_busy = True
        if self.dialog is not None and self.dialog.winfo_exists():
            self.test_button.configure(state='disabled')
        self.log('正在发送测试邮件…')
        def worker():
            try:
                result = reminders.send_email(config, '广东医宿舍水电｜SMTP 测试邮件',
                    f'这是一封由宿舍水电查询工具发送的测试邮件。\n时间：{reminders.now_local():%Y-%m-%d %H:%M:%S}（北京时间）\n收到此邮件说明 SMTP 配置可用于发送。')
                self.events.put((None, 'test_ok', result))
            except Exception as exc:
                self.events.put((None, 'test_error', reminders.error_text(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def target(self):
        bi, ri = self.app.building_box.current(), self.app.room_box.current()
        if bi >= 0 and ri >= 0:
            return self.app.buildings[bi]['id'], self.app.rooms[ri]['id'], self.app.selection_name()
        try:
            building, room = int(self.app.building_id.get()), int(self.app.room_id.get())
            if building <= 0 or room <= 0:
                raise ValueError()
        except ValueError:
            raise ValueError('请先选择宿舍，或填写有效的内部楼栋、房间 ID。') from None
        saved = self.saved_target
        name = saved.get('name') if str(saved.get('building')) == str(building) and str(saved.get('room')) == str(room) else ''
        return building, room, name or f'楼栋 ID {building} / 房间 ID {room}'

    def start(self, automatic=False):
        self.cancel_startup()
        if self.token_validation_busy:
            self.desired_running = True
            self.app.reminder_status.set('正在校验候选 Token，完成后继续启动提醒。')
            return
        if self.active:
            self.log('提醒已在运行。如需修改设置，请先停止。')
            return
        if self.preflight_busy:
            self.log('正在校验凭证，请稍候。')
            return
        try:
            if self.app.busy:
                raise ValueError('请等待当前查询完成后再启动提醒。')
            token = self.app.token.get().strip()
            if not token:
                raise ValueError('请先在主窗口填写 Token。')
            config = reminders.SMTPConfig.from_values(self.values(), self.password.get())
            rules = reminders.Rules.from_values(self.values())
            building, room, name = self.target()
        except ValueError as exc:
            self.app.reminder_status.set(('自动启动未完成：' if automatic else '提醒未启动：') + str(exc))
            self.log(str(exc))
            if not automatic:
                messagebox.showinfo('请检查提醒配置', str(exc), parent=self.dialog or self.root)
            return
        if not self.save_settings(silent=True, validate_auto=False):
            self.app.reminder_status.set('配置保存失败，提醒未启动。请把程序放到可写文件夹。')
            return
        self.desired_running = True
        self.waiting_for_token = False
        self.pending_retarget = False
        self.preflight_busy = True
        self.generation += 1
        generation = self.generation
        cancel = threading.Event()
        self.validation_cancel = cancel
        old_monitor = self.monitor
        self.lock_settings(True)
        self.app.reminder_status.set(f'正在校验 Token 和 SMTP 登录：{name}…')
        self.log(f'准备监测 {name}，正在校验凭证。')
        def validate():
            try:
                if old_monitor is not None:
                    old_monitor.stop()
                    while old_monitor.thread and old_monitor.thread.is_alive():
                        if cancel.wait(.1):
                            return
                if cancel.is_set():
                    return
                info = self.backend.query_balance(token, building, room)
                if cancel.is_set():
                    return
                reminders.check_smtp_login(config)
                if cancel.is_set():
                    return
                self.events.put((generation, 'validated', (token, building, room, name, config, rules, info)))
            except Exception as exc:
                if not cancel.is_set():
                    self.events.put((generation, 'validation_error', (reminders.error_text(exc), automatic)))
        threading.Thread(target=validate, daemon=True).start()

    def activate(self, generation, payload):
        token, building, room, name, config, rules, info = payload
        self.preflight_busy = False
        self.waiting_for_token = False
        self.expired_intent = False
        if not self.desired_running:
            return
        self.monitor = reminders.Monitor(self.backend, token, building, room, name, config, rules,
            lambda kind, data: self.events.put((generation, kind, data)),
            state_path=self.directory / 'reminder-history.json', initial_info=info)
        self.lock_settings(True)
        self.app.reminder_status.set(f'提醒运行中：{name}；每 {rules.interval_minutes} 分钟检查。')
        self.log(f'凭证校验成功，已开始监测：{name}。固定时间使用北京时间。')
        self.monitor.start()

    def stop(self, reason='提醒已停止。'):
        was_active = self.active or self.preflight_busy or self.pending_retarget or self.startup_pending or self.waiting_for_token or self.expired_intent
        self.cancel_startup()
        self.desired_running = False
        self.waiting_for_token = False
        self.expired_intent = False
        self.pending_token_resume = False
        self.pending_retarget = False
        self.preflight_busy = False
        self.validation_cancel.set()
        if self.monitor is not None:
            self.monitor.stop()
        self.generation += 1
        self.lock_settings(False)
        if was_active:
            self.app.reminder_status.set(reason)
            self.log(reason)

    def pause_for_selection(self, reason):
        if not (self.active or self.desired_running or self.preflight_busy or self.startup_pending):
            return
        self.cancel_startup()
        if self.pending_retarget and not self.active and not self.preflight_busy:
            return
        self.desired_running = True
        self.pending_retarget = True
        self.preflight_busy = False
        self.validation_cancel.set()
        if self.monitor is not None:
            self.monitor.stop()
        self.generation += 1
        self.lock_settings(False)
        text = reason + ' 选好新房间后会自动继续提醒。'
        self.app.reminder_status.set(text)
        self.log(text)

    def resume_for_selection(self):
        self.save_settings(silent=True, validate_auto=False)
        if self.desired_running and self.pending_retarget:
            self.start(automatic=True)

    def poll(self):
        if self.app.closed:
            return
        try:
            while True:
                generation, kind, data = self.events.get_nowait()
                if kind.startswith('test_'):
                    self.test_busy = False
                    if self.dialog is not None and self.dialog.winfo_exists():
                        self.test_button.configure(state='normal')
                    if kind == 'test_error':
                        self.log('测试邮件失败：' + data)
                        messagebox.showerror('测试邮件失败', data, parent=self.dialog or self.root)
                    else:
                        text = f'测试邮件已提交 SMTP 服务器，接受 {data["accepted"]} 个、拒绝 {data["refused"]} 个收件人。请检查收件箱或垃圾邮件。'
                        self.log(text)
                        messagebox.showinfo('测试邮件结果', text, parent=self.dialog or self.root)
                    continue
                if kind in ('sync_valid', 'sync_error'):
                    if generation != self.token_sync_epoch:
                        continue
                    self.token_validation_busy = False
                    if kind == 'sync_valid':
                        self.apply_synced_token(*data)
                    else:
                        self.sync_note('候选 Token 验证失败，保留原凭证：' + data)
                    continue
                if generation != self.generation:
                    continue
                if kind == 'validated':
                    self.activate(generation, data)
                elif kind == 'validation_error':
                    self.preflight_busy = False
                    self.pending_retarget = False
                    self.lock_settings(False)
                    text, automatic = data
                    self.expired_intent = '登录凭证已失效' in text
                    self.waiting_for_token = self.vars['token_sync_enabled'].get() and self.expired_intent
                    self.desired_running = self.waiting_for_token
                    self.log('凭证校验失败：' + text)
                    self.app.reminder_status.set('Token 失效，等待小程序重新登录后自动续上提醒。' if self.waiting_for_token else '提醒已暂停：' + text)
                    if not automatic and not self.waiting_for_token:
                        messagebox.showerror('凭证校验未通过', text, parent=self.dialog or self.root)
                elif kind == 'balance':
                    info = data['info']
                    self.app.result_room.set(data['name'])
                    for variable, key in ((self.app.electricity, 'electricityBalance'), (self.app.water, 'waterBalance')):
                        value = info.get(key)
                        variable.set('未提供' if value is None or value == '' else str(value))
                    self.app.updated.set(f'自动查询成功于 {data["time"]:%Y-%m-%d %H:%M:%S}（北京时间）')
                else:
                    self.log(data)
                    self.app.reminder_status.set(data)
                    if kind == 'stopped':
                        self.expired_intent = self.desired_running and 'Token 已失效' in data
                        self.waiting_for_token = self.vars['token_sync_enabled'].get() and self.expired_intent
                        self.desired_running = self.waiting_for_token
                        self.pending_retarget = False
                        self.lock_settings(False)
                        if self.waiting_for_token:
                            self.app.reminder_status.set('Token 失效，等待微信小程序重新登录；新 Token 到达后自动继续。')
        except queue.Empty:
            pass
        self.pump_token_sync()
        if self.pending_token_resume and self.desired_running and not self.app.busy and not self.preflight_busy and not self.token_validation_busy:
            self.pending_token_resume = False
            self.start(automatic=True)
        if not self.app.closed:
            self.poll_timer = self.root.after(250, self.poll)

    def close_dialog(self):
        if self.dialog is not None:
            self.dialog.destroy()
        self.dialog, self.log_widget = None, None
        self.settings_widgets = []

    def close(self):
        self.root.after_cancel(self.poll_timer)
        self.cancel_startup()
        self.token_sync_epoch += 1
        self.token_inbox.close()
        if not self.config_error:
            self.save_settings(silent=True, validate_auto=False)
        self.stop()
        self.password.set('')
