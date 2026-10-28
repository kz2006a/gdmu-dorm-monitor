"""Local desktop UI for choosing an authorized dorm and querying its balance."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import urllib.error

try:
    import gdmu_balance as api
except (ImportError, SystemExit):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror('缺少运行依赖', '请先运行：\npython -m pip install cryptography\n\n并确保 gdmu_balance.py 与窗口程序放在同一目录。')
    root.destroy()
    raise SystemExit(1)


class BalanceApp:
    def __init__(self, root, backend=api, config_dir=None, auto_start=True):
        self.root, self.api = root, backend
        self.busy = False
        self.closed = False
        self.events = queue.Queue()
        self.campuses, self.buildings, self.rooms = [], [], []
        self.editable = []
        self.buttons = []
        self.token = tk.StringVar(value=os.environ.get('GDMU_TOKEN', ''))
        self.status = tk.StringVar(value='先填写 Token，然后点击“加载宿舍列表”。')
        self.electricity = tk.StringVar(value='—')
        self.water = tk.StringVar(value='—')
        self.result_room = tk.StringVar(value='尚未查询')
        self.updated = tk.StringVar(value='选择其他宿舍时，会清除上一次的余量。')
        self.building_id = tk.StringVar(value='1')
        self.room_id = tk.StringVar(value='1')
        self.reminder_status = tk.StringVar(value='邮件提醒未启动。先配置 SMTP 服务与提醒规则。')
        self.reminders = None
        self.sync_status = tk.StringVar(value='未启用 Token 自动同步。')
        self.syncing_target = False
        root.title('广东医 · 宿舍水电查询 v1.4.1')
        height = max(600, min(860, root.winfo_screenheight() - 100))
        root.geometry(f'820x{height}')
        root.minsize(720, 600)
        root.configure(bg='#f3f6fb')
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10), background='#f3f6fb')
        style.configure('TEntry', padding=7)
        style.configure('TCombobox', padding=7)
        style.configure('TButton', padding=(13, 8))
        style.configure('Primary.TButton', background='#2167e8', foreground='white', borderwidth=0)
        style.map('Primary.TButton', background=[('active', '#1857c9'), ('disabled', '#9fb5db')])
        style.configure('TCheckbutton', background='#f3f6fb')
        self.build_ui()
        from gdmu_mail_ui import ReminderController
        self.reminders = ReminderController(self, backend, config_dir=config_dir, auto_start=auto_start)
        self.sync_check.configure(variable=self.reminders.vars['token_sync_enabled'])
        self.last_token_value = self.token.get()
        self.building_id.trace_add('write', self.manual_target_changed)
        self.room_id.trace_add('write', self.manual_target_changed)
        self.poll_timer = self.root.after(100, self.poll)

    def label(self, parent, text, **kwargs):
        opts = dict(bg=parent.cget('bg'), fg='#23334d', font=('Microsoft YaHei UI', 10))
        opts.update(kwargs)
        return tk.Label(parent, text=text, **opts)

    def button(self, parent, text, command, primary=False):
        item = ttk.Button(parent, text=text, command=command,
                          style='Primary.TButton' if primary else 'TButton')
        self.buttons.append(item)
        return item

    def build_ui(self):
        header = tk.Frame(self.root, bg='#152b4b', padx=28, pady=20)
        header.pack(fill='x')
        self.label(header, '宿舍水电查询', fg='white', font=('Microsoft YaHei UI', 23, 'bold')).pack(anchor='w')
        self.label(header, '切换校区、楼栋和房间，查询对应宿舍的水电余量。', fg='#c4d3e9').pack(anchor='w', pady=(6, 0))
        footer = tk.Frame(self.root, bg='#e8eef7', padx=28, pady=10)
        footer.pack(fill='x', side='bottom')
        self.label(footer, '', textvariable=self.status, fg='#526581', anchor='w', wraplength=660).pack(fill='x')
        container = tk.Frame(self.root, bg='#f3f6fb')
        container.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(container, bg='#f3f6fb', highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(self.canvas, bg='#f3f6fb', padx=28, pady=18)
        window = self.canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(window, width=event.width))
        self.root.bind('<MouseWheel>', self.scroll)
        self.label(body, '登录凭证', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
        token_row = tk.Frame(body, bg='#f3f6fb')
        token_row.pack(fill='x', pady=(8, 3))
        self.token_entry = ttk.Entry(token_row, textvariable=self.token, show='●')
        self.token_entry.pack(side='left', fill='x', expand=True)
        self.editable.append(self.token_entry)
        self.button(token_row, '清空', self.clear_token).pack(side='left', padx=(8, 0))
        self.button(token_row, '保存配置', lambda: self.reminders.save_settings()).pack(side='left', padx=(8, 0))
        self.show_token = tk.BooleanVar(value=False)
        self.token_check = ttk.Checkbutton(token_row, text='显示', variable=self.show_token,
                                          command=lambda: self.token_entry.configure(show='' if self.show_token.get() else '●'))
        self.token_check.pack(side='left', padx=(8, 0))
        self.token_entry.bind('<KeyRelease>', self.token_changed)
        self.token_entry.bind('<<Paste>>', lambda event: self.root.after_idle(self.token_changed))
        self.label(body, 'Token 可保存到软件目录 .env，重启自动读取；保存选项位于 SMTP 与提醒设置。', fg='#728096', font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        sync = tk.Frame(body, bg='#f3f6fb')
        sync.pack(fill='x', pady=(10, 0))
        self.sync_check = ttk.Checkbutton(sync, text='接收新 Token', command=lambda: self.reminders.sync_changed())
        self.sync_check.pack(side='left')
        ttk.Button(sync, text='内置同步设置', command=lambda: self.reminders.embedded.open()).pack(side='left', padx=8)
        ttk.Button(sync, text='接入说明', command=lambda: self.reminders.show_sync_help()).pack(side='left')
        self.label(body, '', textvariable=self.sync_status, fg='#526581', font=('Microsoft YaHei UI', 9), wraplength=650, justify='left').pack(anchor='w', pady=(5, 0))

        select_header = tk.Frame(body, bg='#f3f6fb')
        select_header.pack(fill='x', pady=(18, 7))
        self.label(select_header, '选择宿舍', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        self.button(select_header, '加载宿舍列表', self.load_campuses).pack(side='right')
        selects = tk.Frame(body, bg='#f3f6fb')
        selects.pack(fill='x')
        self.combos = []
        for col, title in enumerate(('校区', '楼栋', '房间')):
            selects.columnconfigure(col, weight=1, uniform='select')
            block = tk.Frame(selects, bg='#f3f6fb')
            block.grid(row=0, column=col, sticky='ew', padx=(0 if col == 0 else 8, 0))
            self.label(block, title, fg='#728096').pack(anchor='w', pady=(0, 5))
            combo = ttk.Combobox(block, state='disabled', width=18)
            combo.pack(fill='x')
            self.combos.append(combo)
        self.campus_box, self.building_box, self.room_box = self.combos
        self.campus_box.bind('<<ComboboxSelected>>', self.choose_campus)
        self.building_box.bind('<<ComboboxSelected>>', self.choose_building)
        self.room_box.bind('<<ComboboxSelected>>', self.choose_room)
        self.button(body, '查询所选宿舍', self.query_selected, primary=True).pack(anchor='e', pady=(12, 14))

        card = tk.Frame(body, bg='white', padx=20, pady=16, highlightbackground='#e0e7f1', highlightthickness=1)
        card.pack(fill='x')
        self.label(card, '', textvariable=self.result_room, font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
        meters = tk.Frame(card, bg='white')
        meters.pack(fill='x', pady=(14, 9))
        for col, (title, value, unit, color) in enumerate((
            ('剩余电量', self.electricity, '度', '#2167e8'),
            ('剩余水量', self.water, '吨', '#078a9b'),
        )):
            meters.columnconfigure(col, weight=1, uniform='meters')
            section = tk.Frame(meters, bg='white')
            section.grid(row=0, column=col, sticky='w')
            self.label(section, title, fg='#728096').pack(anchor='w')
            line = tk.Frame(section, bg='white')
            line.pack(anchor='w')
            self.label(line, '', textvariable=value, fg=color, font=('Microsoft YaHei UI', 30, 'bold')).pack(side='left')
            self.label(line, unit, fg='#728096').pack(side='left', padx=(8, 0), pady=(14, 0))
        self.label(card, '', textvariable=self.updated, fg='#728096', font=('Microsoft YaHei UI', 9)).pack(anchor='w')

        remind = tk.Frame(body, bg='#f3f6fb')
        remind.pack(fill='x', pady=(15, 0))
        self.label(remind, '邮件提醒', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
        controls = tk.Frame(remind, bg='#f3f6fb')
        controls.pack(fill='x', pady=(8, 6))
        ttk.Button(controls, text='SMTP 与提醒设置', command=lambda: self.reminders.open()).pack(side='left')
        ttk.Button(controls, text='开始邮件提醒', style='Primary.TButton', command=lambda: self.reminders.start()).pack(side='left', padx=8)
        ttk.Button(controls, text='停止提醒', command=lambda: self.reminders.stop()).pack(side='left')
        self.label(remind, '', textvariable=self.reminder_status, fg='#526581', wraplength=660, justify='left').pack(anchor='w')
        self.label(remind, '每天固定时间 / 低于余量阈值；需保持程序运行，电脑不休眠。', fg='#728096', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(4, 0))

        manual = tk.Frame(body, bg='#f3f6fb')
        manual.pack(fill='x', pady=(16, 0))
        self.label(manual, '也可直接按内部编号查询', fg='#728096', font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        row = tk.Frame(manual, bg='#f3f6fb')
        row.pack(fill='x', pady=(7, 0))
        for title, variable in (('楼栋 ID', self.building_id), ('房间 ID', self.room_id)):
            self.label(row, title, font=('Microsoft YaHei UI', 9)).pack(side='left', padx=(0, 5))
            entry = ttk.Entry(row, textvariable=variable, width=10)
            entry.pack(side='left', padx=(0, 15))
            self.editable.append(entry)
        self.button(row, '按编号查询', self.query_manual).pack(side='right')
        self.label(body, '电余量每半小时更新；水余量每天 14:00 更新（以小程序说明为准）。', fg='#728096', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(14, 0))

    def scroll(self, event):
        if not isinstance(event.widget, ttk.Combobox) and event.delta:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def reset_result(self, label='尚未查询'):
        self.electricity.set('—')
        self.water.set('—')
        self.result_room.set(label)
        self.updated.set('尚未获得该宿舍的最新查询结果。')

    def reset_combo(self, combo):
        combo.configure(values=(), state='disabled')
        combo.set('')

    def clear_token(self):
        self.token.set('')
        self.token_changed()

    def token_changed(self, event=None):
        if self.busy:
            return
        if self.token.get() == self.last_token_value:
            return
        self.last_token_value = self.token.get()
        self.stop_for_change('Token 已更改，提醒已停止。更新后请重新启动。')
        self.campuses, self.buildings, self.rooms = [], [], []
        for combo in self.combos:
            self.reset_combo(combo)
        self.reset_result()
        self.status.set('Token 已更改，请重新加载宿舍列表。')

    def set_busy(self, busy):
        self.busy = busy
        for button in self.buttons:
            button.configure(state='disabled' if busy else 'normal')
        for entry in self.editable:
            entry.configure(state='disabled' if busy else 'normal')
        for combo in self.combos:
            combo.configure(state='readonly' if not busy and combo.cget('values') else 'disabled')

    def run(self, description, job, on_success):
        if self.busy:
            return
        if not self.token.get().strip():
            messagebox.showinfo('请填写 Token', '请先粘贴自己查询请求中的 token 值。', parent=self.root)
            self.token_entry.focus_set()
            return
        self.set_busy(True)
        self.status.set(description)
        def worker():
            try:
                self.events.put((True, job(), on_success))
            except Exception as exc:
                self.events.put((False, exc, on_success))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                success, data, callback = self.events.get_nowait()
                self.set_busy(False)
                if success:
                    callback(data)
                else:
                    if isinstance(data, urllib.error.HTTPError):
                        text = f'HTTP {data.code}，请检查 Token 和网络。'
                    elif isinstance(data, (urllib.error.URLError, TimeoutError, OSError)):
                        text = '无法连接缴费站点，请检查网络、代理与证书配置。'
                    else:
                        text = str(data)
                    self.status.set('操作失败：' + text)
                    messagebox.showerror('查询未完成', text, parent=self.root)
        except queue.Empty:
            pass
        if not self.closed:
            self.poll_timer = self.root.after(100, self.poll)

    def fill(self, combo, items):
        names = [item['name'] for item in items]
        # Keep duplicate display names distinguishable without changing the IDs.
        combo.configure(values=[f"{item['name']}（{item['id']}）" if names.count(item['name']) > 1 else item['name'] for item in items],
                        state='readonly' if items else 'disabled')
        combo.set('')

    def load_campuses(self):
        self.stop_for_change('正在重新选择宿舍，监测已暂停。', allow_resume=True)
        self.campuses, self.buildings, self.rooms = [], [], []
        for combo in self.combos:
            self.reset_combo(combo)
        self.reset_result()
        token = self.token.get().strip()
        def done(items):
            self.campuses = items
            self.fill(self.campus_box, items)
            self.status.set('请选择校区。' if items else '当前账号没有可用校区。')
        self.run('正在加载校区…', lambda: self.api.list_campuses(token), done)

    def choose_campus(self, event=None):
        self.stop_for_change('校区已切换，监测已暂停。', allow_resume=True)
        self.buildings, self.rooms = [], []
        self.reset_combo(self.building_box)
        self.reset_combo(self.room_box)
        self.reset_result()
        index = self.campus_box.current()
        if index < 0:
            return
        campus = self.campuses[index]
        token = self.token.get().strip()
        def done(items):
            self.buildings = items
            self.fill(self.building_box, items)
            self.status.set('请选择楼栋。' if items else '该校区暂无可用楼栋。')
        self.run('正在加载楼栋…', lambda: self.api.list_buildings(token, campus['id']), done)

    def choose_building(self, event=None):
        self.stop_for_change('楼栋已切换，监测已暂停。', allow_resume=True)
        self.rooms = []
        self.reset_combo(self.room_box)
        self.reset_result()
        ci, bi = self.campus_box.current(), self.building_box.current()
        if ci < 0 or bi < 0:
            return
        campus, building = self.campuses[ci], self.buildings[bi]
        token = self.token.get().strip()
        def done(items):
            self.rooms = items
            self.fill(self.room_box, items)
            self.status.set('请选择房间，再点击“查询所选宿舍”。' if items else '该楼栋暂无可用房间。')
        self.run('正在加载房间…', lambda: self.api.list_rooms(token, campus['id'], building['id']), done)

    def choose_room(self, event=None):
        self.stop_for_change('房间已切换，正在切换监测目标。', allow_resume=True)
        self.reset_result(self.selection_name())
        bi, ri = self.building_box.current(), self.room_box.current()
        if bi >= 0 and ri >= 0:
            self.syncing_target = True
            try:
                self.building_id.set(str(self.buildings[bi]['id']))
                self.room_id.set(str(self.rooms[ri]['id']))
            finally:
                self.syncing_target = False
            if self.reminders:
                self.reminders.resume_for_selection()
        self.status.set('已切换宿舍，点击“查询所选宿舍”获取余量。')

    def selection_name(self):
        return ' / '.join(box.get() for box in self.combos if box.get()) or '尚未选择宿舍'

    def query_selected(self):
        bi, ri = self.building_box.current(), self.room_box.current()
        if bi < 0 or ri < 0:
            messagebox.showinfo('请选择宿舍', '请依次选择校区、楼栋和房间。', parent=self.root)
            return
        self.query(self.buildings[bi]['id'], self.rooms[ri]['id'], self.selection_name())

    def query_manual(self):
        try:
            building, room = int(self.building_id.get()), int(self.room_id.get())
            if building <= 0 or room <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showinfo('编号格式不正确', '请填写正整数形式的楼栋 ID 与房间 ID；它们不是楼号或门牌号。', parent=self.root)
            return
        self.query(building, room, f'楼栋 ID {building} / 房间 ID {room}')

    def query(self, building, room, name):
        if self.reminders and self.reminders.active:
            current = self.reminders.monitor
            if str(current.building) != str(building) or str(current.room) != str(room):
                self.stop_for_change('正在切换监测宿舍。', allow_resume=True)
        self.reset_result(name)
        token = self.token.get().strip()
        def done(info):
            electric, water = info.get('electricityBalance'), info.get('waterBalance')
            self.electricity.set('未提供' if electric is None or electric == '' else str(electric))
            self.water.set('未提供' if water is None or water == '' else str(water))
            self.updated.set('查询成功于 ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '；读数更新时间以上游为准。')
            self.status.set('查询完成。可重新选择校区、楼栋或房间。')
            if self.reminders and self.reminders.pending_retarget:
                self.reminders.resume_for_selection()
        self.run('正在查询水电余量…', lambda: self.api.query_balance(token, building, room), done)

    def close(self):
        if self.reminders:
            self.reminders.close()
        self.closed = True
        self.root.after_cancel(self.poll_timer)
        self.token.set('')
        self.root.destroy()

    def stop_for_change(self, reason, allow_resume=False):
        if self.reminders:
            if allow_resume:
                self.reminders.pause_for_selection(reason)
            elif self.reminders.active or self.reminders.preflight_busy or self.reminders.pending_retarget or self.reminders.startup_pending or self.reminders.waiting_for_token or self.reminders.token_validation_busy or self.reminders.expired_intent:
                self.reminders.stop(reason)

    def manual_target_changed(self, *args):
        if not self.syncing_target:
            self.stop_for_change('内部编号已修改；点击按编号查询后继续监测。', allow_resume=True)


if __name__ == '__main__':
    root = tk.Tk()
    BalanceApp(root)
    root.mainloop()
