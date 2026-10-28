"""Desktop workflow: login -> lists -> exact saved selection -> query."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
import urllib.error
import time
import gdmu_balance as api


class BalanceApp:
    def __init__(self, root, backend=api, config_dir=None, auto_start=True):
        self.root, self.api = root, backend
        self.busy = self.closed = False
        self.events = queue.Queue()
        self.request_epoch = 0
        self.campuses, self.buildings, self.rooms = [], [], []
        self.editable, self.buttons = [], []
        self.token = tk.StringVar(value=os.environ.get('GDMU_TOKEN', ''))
        self.status = tk.StringVar(value='连接微信后自动加载宿舍。')
        self.electricity, self.water = tk.StringVar(value='—'), tk.StringVar(value='—')
        self.result_room = tk.StringVar(value='请选择宿舍')
        self.updated = tk.StringVar(value='')
        self.building_id, self.room_id = tk.StringVar(), tk.StringVar()
        self.reminder_status = tk.StringVar(value='未开始监测')
        self.sync_status = tk.StringVar(value='未连接')
        self.reminders = None
        self.syncing_target = self.restoring = self.flow_ready = False
        self.restore_target = {}
        self.token_timer = self.initial_timer = None
        root.title('广东医 · 宿舍水电 v1.7.1')
        root.geometry(f'{max(760,min(1080,root.winfo_screenwidth()-100))}x{max(600,min(820,root.winfo_screenheight()-100))}')
        root.minsize(760,600)
        root.protocol('WM_DELETE_WINDOW',self.close)
        from gdmu_ui import theme, DashboardUI
        theme(root)
        self.ui = DashboardUI(self)
        from gdmu_mail_ui import ReminderController
        self.reminders = ReminderController(self,backend,config_dir=config_dir,auto_start=auto_start)
        self.ui.attach()
        self.last_token_value = self.token.get()
        self.building_id.trace_add('write',self.manual_target_changed)
        self.room_id.trace_add('write',self.manual_target_changed)
        self.poll_timer = root.after(60,self.poll)
        if auto_start and self.token.get().strip() and not self.reminders.config_error:
            self.initial_timer = root.after(100,self.initial_load)

    def initial_load(self):
        self.initial_timer = None
        self.load_campuses()

    def button(self,parent,text,command,primary=False):
        item=ttk.Button(parent,text=text,command=command,style='Primary.TButton' if primary else 'TButton')
        self.buttons.append(item)
        return item

    def scroll(self,event):
        if not isinstance(event.widget,ttk.Combobox) and event.delta:
            self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')

    def reset_result(self,label='请选择宿舍'):
        self.electricity.set('—'); self.water.set('—')
        self.result_room.set(label); self.updated.set('')

    def reset_combo(self,combo):
        combo.configure(values=(),state='disabled'); combo.set('')

    def cancel_requests(self):
        self.request_epoch += 1
        self.set_busy(False)

    def clear_token(self):
        self.token.set(''); self.token_changed(immediate=True)

    def token_changed(self,event=None,immediate=False):
        if self.token.get()==self.last_token_value: return
        self.last_token_value=self.token.get()
        self.cancel_requests()
        self.stop_for_change('登录凭证已更改，监测已停止。')
        self.flow_ready=False
        self.campuses,self.buildings,self.rooms=[],[],[]
        for combo in self.combos: self.reset_combo(combo)
        self.reset_result()
        if self.token_timer: self.root.after_cancel(self.token_timer)
        self.token_timer=None
        if self.token.get().strip():
            self.status.set('正在验证登录并加载宿舍…')
            self.token_timer=self.root.after(1 if immediate else 650,self.manual_login)
        else:
            self.status.set('连接微信后自动加载宿舍。')
            self.reminders.save_session()

    def manual_login(self):
        self.token_timer=None
        self.load_campuses()

    def set_busy(self,busy):
        self.busy=busy
        for button in self.buttons: button.configure(state='disabled' if busy else 'normal')
        for combo in self.combos:
            combo.configure(state='readonly' if not busy and combo.cget('values') else 'disabled')

    def run(self,description,job,on_success,on_error=None):
        if self.busy: return False
        if not self.token.get().strip():
            self.ui.show('login'); self.status.set('请先连接微信。'); return False
        self.set_busy(True); self.status.set(description)
        epoch=self.request_epoch
        def worker():
            try: self.events.put((epoch,True,job(),on_success,on_error))
            except Exception as exc: self.events.put((epoch,False,exc,on_success,on_error))
        threading.Thread(target=worker,daemon=True).start()
        return True

    def fail(self,exc):
        self.flow_ready=False
        if isinstance(exc,urllib.error.HTTPError): text=f'HTTP {exc.code}，请检查网络或重新登录。'
        elif isinstance(exc,(urllib.error.URLError,TimeoutError,OSError)): text='网络连接失败，请检查网络后重试。'
        else: text=str(exc)
        self.status.set(text); self.reminders.log('查询流程：'+text)
        if '登录凭证已失效' in text: self.reminders.login_expired()
        self.restoring=False

    def poll(self):
        if self.closed: return
        try:
            for _ in range(20):
                epoch,success,data,callback,on_error=self.events.get_nowait()
                if epoch!=self.request_epoch: continue
                self.set_busy(False)
                if success: callback(data)
                elif on_error: on_error(data)
                else: self.fail(data)
        except queue.Empty: pass
        self.ui.refresh()
        self.poll_timer=self.root.after(60,self.poll)

    def fill(self,combo,items):
        from collections import Counter
        names=Counter(item['name'] for item in items)
        combo.configure(values=[f"{item['name']}（{item['id']}）" if names[item['name']]>1 else item['name'] for item in items],state='readonly' if items else 'disabled')
        combo.set('')

    @staticmethod
    def matching(items,wanted):
        return next((i for i,x in enumerate(items) if str(x['id'])==str(wanted)),-1)

    def load_campuses(self,prefetched=None):
        if self.busy: return
        self.stop_for_change('正在加载宿舍，监测暂时暂停。',allow_resume=True)
        self.flow_ready=False
        self.restore_target=dict(self.reminders.saved_target)
        self.restoring=bool(self.restore_target.get('building') and self.restore_target.get('room'))
        self.campuses,self.buildings,self.rooms=[],[],[]
        for combo in self.combos: self.reset_combo(combo)
        self.reset_result('正在恢复上次宿舍' if self.restoring else '请选择宿舍')
        token=self.token.get().strip()
        def done(items):
            self.campuses=items; self.fill(self.campus_box,items)
            self.reminders.save_settings(silent=True,validate_auto=False)
            index=self.matching(items,self.restore_target.get('campus')) if self.restoring else -1
            if self.restoring and index<0 and not self.restore_target.get('campus'):
                self.restore_legacy(items,token); return
            if self.restoring and index<0:
                self.restoration_missing('上次校区已不可用，请重新选择。'); return
            if index<0 and len(items)==1: index=0
            if index>=0:
                self.campus_box.current(index); self.choose_campus(restore=True)
            else: self.status.set('请选择校区。' if items else '当前账号没有可用校区。')
            self.ui.show('overview')
        if prefetched is not None: done(prefetched)
        else: self.run('正在加载宿舍…',lambda:self.api.list_campuses(token),done)

    def restore_legacy(self,campuses,token):
        wanted=self.restore_target.get('building')
        def search():
            for ci,campus in enumerate(campuses):
                items=self.api.list_buildings(token,campus['id'])
                if self.matching(items,wanted)>=0: return ci,items
            return None
        def done(found):
            if found is None:
                self.restoration_missing('上次楼栋已不可用，请重新选择。'); return
            ci,items=found; self.campus_box.current(ci); self.buildings_loaded(items,True)
        self.run('正在匹配旧版保存的宿舍…',search,done)

    def restoration_missing(self,reason):
        self.reminders.finish_recovery(queried=False)
        self.restoring=False; self.flow_ready=False
        self.reset_result('请重新选择宿舍'); self.status.set(reason); self.ui.show('overview')
        if self.reminders.desired_running:
            self.reminders.pending_retarget=True
            self.reminder_status.set('等待选择宿舍后继续监测')

    def choose_campus(self,event=None,restore=False):
        if not restore: self.restoring=False
        self.stop_for_change('校区已切换。',allow_resume=True)
        self.flow_ready=False; self.buildings,self.rooms=[],[]
        for combo in (self.building_box,self.room_box): self.reset_combo(combo)
        self.reset_result()
        index=self.campus_box.current()
        if index<0: return
        campus=self.campuses[index]; token=self.token.get().strip()
        self.run('正在加载楼栋…',lambda:self.api.list_buildings(token,campus['id']),lambda items:self.buildings_loaded(items,restore))

    def buildings_loaded(self,items,restore):
        self.buildings=items; self.fill(self.building_box,items)
        index=self.matching(items,self.restore_target.get('building')) if restore and self.restoring else -1
        if self.restoring and index<0:
            self.restoration_missing('上次楼栋已不可用，请重新选择。'); return
        if index<0 and len(items)==1: index=0
        if index>=0:
            self.building_box.current(index); self.choose_building(restore=restore)
        else: self.status.set('请选择楼栋。' if items else '该校区暂无可用楼栋。')

    def choose_building(self,event=None,restore=False):
        if not restore: self.restoring=False
        self.stop_for_change('楼栋已切换。',allow_resume=True)
        self.flow_ready=False; self.rooms=[]; self.reset_combo(self.room_box); self.reset_result()
        ci,bi=self.campus_box.current(),self.building_box.current()
        if ci<0 or bi<0: return
        campus,building=self.campuses[ci],self.buildings[bi]; token=self.token.get().strip()
        def done(items):
            self.rooms=items; self.fill(self.room_box,items)
            index=self.matching(items,self.restore_target.get('room')) if self.restoring else -1
            if self.restoring and index<0:
                self.restoration_missing('上次房间已不可用，请重新选择。'); return
            if index<0 and len(items)==1: index=0
            if index>=0:
                self.room_box.current(index); self.choose_room()
            else: self.status.set('请选择房间，选择后自动查询。' if items else '该楼栋暂无可用房间。')
        self.run('正在加载房间…',lambda:self.api.list_rooms(token,campus['id'],building['id']),done)

    def choose_room(self,event=None):
        bi,ri=self.building_box.current(),self.room_box.current()
        if bi<0 or ri<0: return
        self.stop_for_change('宿舍已切换。',allow_resume=True)
        self.restoring=False; self.flow_ready=True
        self.syncing_target=True
        try:
            self.building_id.set(str(self.buildings[bi]['id'])); self.room_id.set(str(self.rooms[ri]['id']))
        finally: self.syncing_target=False
        self.reminders.save_session()
        self.query_selected()

    def selection_name(self):
        return ' / '.join(box.get() for box in self.combos if box.get()) or '尚未选择宿舍'

    def selected_target(self):
        ci,bi,ri=[box.current() for box in self.combos]
        if min(ci,bi,ri)<0: return None
        campus,building,room=self.campuses[ci],self.buildings[bi],self.rooms[ri]
        return {'campus':campus['id'],'building':building['id'],'room':room['id'],'campus_name':campus['name'],'building_name':building['name'],'room_name':room['name'],'name':self.selection_name()}

    def query_selected(self):
        bi,ri=self.building_box.current(),self.room_box.current()
        if bi<0 or ri<0:
            if not self.campuses: self.load_campuses()
            else: self.status.set('请先选择宿舍。')
            return
        self.query(self.buildings[bi]['id'],self.rooms[ri]['id'],self.selection_name())

    def query_manual(self):
        try:
            building,room=int(self.building_id.get()),int(self.room_id.get())
            if min(building,room)<=0: raise ValueError()
        except ValueError:
            self.status.set('内部编号需填写正整数。'); return
        self.stop_for_change('正在切换到内部编号查询。',allow_resume=True)
        for combo in self.combos: self.reset_combo(combo)
        self.flow_ready=True
        self.query(building,room,f'楼栋 ID {building} / 房间 ID {room}')

    def query(self,building,room,name):
        if self.busy: return
        token=self.token.get().strip(); self.reset_result(name)
        def done(info):
            self.last_balance=(token,str(building),str(room),info,time.monotonic())
            self.display_balance(info,name)
            self.flow_ready=True
            self.reminders.finish_recovery()
            saved=self.reminders.save_session()
            self.status.set('已更新 · 宿舍已保存在本地' if saved else '余量已更新，但本地保存失败，请检查配置目录。')
            self.reminders.resume_for_selection()
        self.run('正在查询水电余量…',lambda:self.api.query_balance(token,building,room),done)

    def display_balance(self,info,name):
        self.result_room.set(name)
        for variable,key in ((self.electricity,'electricityBalance'),(self.water,'waterBalance')):
            value=info.get(key); variable.set('未提供' if value is None or value=='' else str(value))
        self.updated.set('更新于 '+datetime.now().strftime('%m-%d %H:%M:%S'))

    def close(self):
        if self.closed: return
        self.root._ui_closing=True
        if self.reminders: self.reminders.close()
        self.closed=True
        for timer in (self.poll_timer,self.token_timer,self.initial_timer):
            if timer: self.root.after_cancel(timer)
        # Deferred wrapping/layout callbacks belong to widgets in this interpreter.
        # Cancel before destroy so repeated open/close never leaves Tcl callbacks.
        for timer in self.root.tk.splitlist(self.root.tk.call('after','info')):
            self.root.tk.call('after','cancel',timer)
        self.token.set(''); self.root.destroy()

    def stop_for_change(self,reason,allow_resume=False):
        if self.reminders:
            if allow_resume: self.reminders.pause_for_selection(reason)
            elif self.reminders.active or self.reminders.desired_running or self.reminders.startup_pending or self.reminders.token_validation_busy:
                self.reminders.stop(reason)

    def manual_target_changed(self,*args):
        if not self.syncing_target:
            self.flow_ready=False; self.stop_for_change('内部编号已修改。',allow_resume=True)


if __name__=='__main__':
    root=tk.Tk(); BalanceApp(root); root.mainloop()
