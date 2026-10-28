"""Mail settings window and bridge between the UI and reminder worker."""
from datetime import datetime
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import gdmu_reminders as reminders

DEFAULTS = {
    'host': '', 'port': '465', 'security': 'SSL/TLS', 'username': '',
    'sender': '', 'recipients': '', 'daily_enabled': False,
    'daily_times': '08:00, 20:00', 'threshold_enabled': True,
    'electricity_limit': '20', 'water_limit': '1',
    'interval_minutes': '30', 'repeat_hours': '24',
}


class ReminderController:
    def __init__(self, app, backend, config_dir=None):
        self.app, self.root, self.backend = app, app.root, backend
        self.directory = Path(config_dir) if config_dir else Path(os.environ.get(
            'LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'GDMUDormMonitor'
        saved = reminders.load_json(self.directory / 'settings.json')
        self.vars = {}
        for key, default in DEFAULTS.items():
            value = saved.get(key, default)
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(self.root, value=value if isinstance(value, bool) else default)
            else:
                self.vars[key] = tk.StringVar(self.root, value=str(value))
        self.password = tk.StringVar(self.root)
        self.events = queue.Queue()
        self.monitor = None
        self.generation = 0
        self.dialog = None
        self.settings_widgets = []
        self.log_widget = None
        self.logs = []
        self.test_busy = False
        self.root.after(250, self.poll)

    @property
    def active(self):
        return self.monitor is not None and not self.monitor.stop_event.is_set()

    def values(self):
        return {key: variable.get() for key, variable in self.vars.items()}

    def save_settings(self):
        try:
            reminders.save_json(self.directory / 'settings.json', self.values())
        except OSError:
            messagebox.showerror('保存失败', '普通设置无法写入本机配置目录。', parent=self.dialog or self.root)
            return
        self.log('普通设置已保存，未保存 Token 或 SMTP 密码 / 授权码。')

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
        ttk.Button(actions, text='保存普通设置', command=self.save_settings).pack(side='left')
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
        ttk.Label(smtp, text='密码 / 授权码只在本次运行内使用，不写入配置文件。', foreground='#728096', wraplength=600).grid(row=9, column=0, columnspan=2, sticky='w', pady=(5, 0))

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
        ttk.Label(rules, text='提醒绑定启动时的宿舍。修改设置前请停止提醒，修改后重新启动。\n程序关闭、电脑关机或休眠期间无法执行查询和发送。最小化窗口可继续运行。', foreground='#526581', wraplength=610).grid(row=10, column=0, columnspan=2, sticky='w', pady=(8, 0))

        logbox = ttk.LabelFrame(body, text='运行记录', padding=10)
        logbox.pack(fill='x', pady=(14, 0))
        self.log_widget = tk.Text(logbox, height=7, wrap='word', font=('Microsoft YaHei UI', 9), relief='flat')
        self.log_widget.pack(fill='x')
        self.log_widget.insert('end', '\n'.join(self.logs) or '尚未启动提醒。可先发送测试邮件，验证 SMTP 配置。')
        self.log_widget.configure(state='disabled')
        self.lock_settings(self.active)
        self.test_button.configure(state='disabled' if self.test_busy else 'normal')

    def rule_field(self, parent, row, title, key):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        field = ttk.Entry(parent, textvariable=self.vars[key])
        field.grid(row=row, column=1, sticky='ew', pady=4)
        self.settings_widgets.append(field)

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
        return building, room, f'楼栋 ID {building} / 房间 ID {room}'

    def start(self):
        if self.active:
            self.log('提醒已在运行。如需修改设置，请先停止。')
            return
        if self.monitor is not None and self.monitor.thread and self.monitor.thread.is_alive():
            messagebox.showinfo('正在停止', '上一轮查询或发送正在退出，请稍后再启动。', parent=self.dialog or self.root)
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
            messagebox.showinfo('请检查提醒配置', str(exc), parent=self.dialog or self.root)
            return
        self.generation += 1
        generation = self.generation
        self.monitor = reminders.Monitor(self.backend, token, building, room, name, config, rules,
            lambda kind, data: self.events.put((generation, kind, data)),
            state_path=self.directory / 'reminder-history.json')
        self.lock_settings(True)
        self.app.reminder_status.set(f'提醒运行中：{name}；每 {rules.interval_minutes} 分钟检查。')
        self.log(f'已开始监测：{name}。固定时间使用北京时间。')
        self.monitor.start()

    def stop(self, reason='提醒已停止。'):
        was_active = self.active
        if self.monitor is not None:
            self.monitor.stop()
        self.generation += 1
        self.lock_settings(False)
        if was_active:
            self.app.reminder_status.set(reason)
            self.log(reason)

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
                if generation != self.generation:
                    continue
                if kind == 'balance':
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
                        self.lock_settings(False)
        except queue.Empty:
            pass
        self.root.after(250, self.poll)

    def close_dialog(self):
        if self.dialog is not None:
            self.dialog.destroy()
        self.dialog, self.log_widget = None, None
        self.settings_widgets = []

    def close(self):
        self.stop()
        self.password.set('')
