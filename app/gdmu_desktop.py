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
        self.reminder_status = tk.StringVar(value='持续监测未启动。可直接使用 Windows 通知，邮箱为可选项。')
        self.reminders = None
        self.sync_status = tk.StringVar(value='未启用 Token 自动同步。')
        self.syncing_target = False
        root.title('广东医 · 宿舍水电查询 v1.6.0')
        width = max(760, min(1120, root.winfo_screenwidth() - 100))
        height = max(600, min(870, root.winfo_screenheight() - 100))
        root.geometry(f'{width}x{height}')
        root.minsize(760, 600)
        root.protocol('WM_DELETE_WINDOW', self.close)
        from gdmu_ui import theme
        theme(root)
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
        from gdmu_ui import DashboardUI
        self.ui = DashboardUI(self)

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
            self.ui.show('login')
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
        self.ui.refresh()
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
