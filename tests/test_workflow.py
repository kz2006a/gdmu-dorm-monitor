from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from pathlib import Path
import sys, tempfile, time, threading, unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'app'
sys.path.insert(0,str(APP))
import gdmu_desktop as gui
from gdmu_config import ConfigStore
import gdmu_reminders as rem

class Backend:
    def __init__(self):
        self.good={'old','new'}; self.calls=[]; self.missing=False
        self.block=None; self.entered=threading.Event(); self.release=threading.Event()
    def check(self,token):
        if token==self.block:
            self.entered.set(); self.release.wait(3)
        if token not in self.good: raise ValueError('登录凭证已失效，请更新。')
    def list_campuses(self,token):
        self.calls.append(('campuses',token)); self.check(token)
        return [{'id':1,'name':'校区甲'},{'id':2,'name':'校区乙'}]
    def list_buildings(self,token,campus):
        self.calls.append(('buildings',token,campus)); self.check(token)
        return [{'id':10,'name':'一栋'},{'id':11,'name':'二栋'}] if str(campus)=='1' else [{'id':20,'name':'二栋'}]
    def list_rooms(self,token,campus,building):
        self.calls.append(('rooms',token,campus,building)); self.check(token)
        return [{'id':100,'name':'101'},{'id':101 if not self.missing else 102,'name':'102'}] if str(building)=='10' else [{'id':200,'name':'201'}]
    def query_balance(self,token,building,room):
        self.calls.append(('balance',token,str(building),str(room))); self.check(token)
        return {'electricityBalance':str(room),'waterBalance':'8.5'}

class Flow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests/.tmp')
        self.backend=Backend(); self.apps=[]
        self.app=self.make(False); self.ctl=self.app.reminders
        self.ctl.vars['desktop_enabled'].set(False)
        self.ctl.vars['email_enabled'].set(False)
    def make(self,automatic):
        root=gui.tk.Tk(); root.withdraw()
        app=gui.BalanceApp(root,self.backend,config_dir=self.temp.name,auto_start=automatic)
        self.apps.append(app); return app
    def tearDown(self):
        self.backend.release.set()
        for app in self.apps:
            if not app.closed: app.close()
        self.temp.cleanup()
    def wait(self,predicate,timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            for app in self.apps:
                if not app.closed: app.root.update()
            if predicate(): return
            time.sleep(.01)
        self.fail(self.app.status.get()+' / '+self.app.reminder_status.get())
    def select(self):
        self.app.token.set('old'); self.app.last_token_value='old'
        self.app.load_campuses(); self.wait(lambda:not self.app.busy)
        self.app.campus_box.current(0); self.app.choose_campus(); self.wait(lambda:not self.app.busy)
        self.app.building_box.current(0); self.app.choose_building(); self.wait(lambda:not self.app.busy)
        self.app.room_box.current(1); self.app.choose_room(); self.wait(lambda:not self.app.busy)
    def test_no_default_target_and_new_token_loads_without_dorm(self):
        self.assertFalse(self.app.building_id.get())
        self.ctl.vars['token_sync_enabled'].set(True)
        self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and len(self.app.campuses)==2)
        self.assertEqual(self.app.ui.page,'overview')
        self.assertEqual([x[0] for x in self.backend.calls],['campuses'])
    def test_selection_saves_all_ids_and_automatically_queries(self):
        self.select()
        self.assertEqual(self.app.electricity.get(),'101')
        saved=ConfigStore(self.temp.name).load()['target']
        self.assertEqual((saved['campus'],saved['building'],saved['room']),('1','10','101'))
    def test_restart_restores_exact_ids_despite_reordered_names(self):
        self.select(); self.app.close()
        original=self.backend.list_rooms
        self.backend.list_rooms=lambda *a:list(reversed(original(*a)))
        app=self.make(True)
        self.wait(lambda:app.electricity.get()=='101')
        self.assertEqual(app.room_box.current(),0)
        self.assertEqual(str(app.selected_target()['room']),'101')
    def test_fresh_capture_restores_and_queries_saved_dorm(self):
        self.select(); self.ctl.vars['token_sync_enabled'].set(True)
        self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and not self.app.busy and self.app.electricity.get()=='101')
        self.assertEqual(self.backend.calls[-1],('balance','new','10','101'))
    def test_missing_saved_room_never_queries_another_dorm(self):
        self.select(); before=len([c for c in self.backend.calls if c[0]=='balance'])
        self.backend.missing=True; self.app.load_campuses()
        self.wait(lambda:not self.app.busy and '不可用' in self.app.status.get())
        self.assertEqual(len([c for c in self.backend.calls if c[0]=='balance']),before)
        self.assertEqual(self.app.room_box.current(),-1)
        self.assertFalse(self.app.flow_ready)
    def test_old_config_without_campus_is_migrated(self):
        self.app.token.set('old'); self.app.last_token_value='old'
        self.ctl.saved_target={'building':'20','room':'200','name':'旧宿舍'}
        self.app.building_id.set('20'); self.app.room_id.set('200')
        self.app.load_campuses(); self.wait(lambda:self.app.electricity.get()=='200')
        self.assertEqual(self.app.campus_box.current(),1)
        self.assertEqual(ConfigStore(self.temp.name).load()['target']['campus'],'2')
    def test_invalid_candidate_does_not_replace_token(self):
        self.app.token.set('old'); self.app.last_token_value='old'
        self.ctl.vars['token_sync_enabled'].set(True); self.ctl.begin_token_update('invalid')
        self.wait(lambda:not self.ctl.token_validation_busy)
        self.assertEqual(self.app.token.get(),'old')
    def test_unfinished_rule_edit_does_not_block_dorm_persistence(self):
        self.ctl.vars['interval_minutes'].set('unfinished')
        self.select()
        self.assertEqual(ConfigStore(self.temp.name).load()['target']['room'],'101')
        self.assertEqual(ConfigStore(self.temp.name).load()['options']['interval_minutes'],'30')
    def test_legacy_blank_sample_target_is_not_a_user_selection(self):
        path=Path(self.temp.name)/'.env'
        path.write_text('CONFIG_VERSION="1.6.0"\nBUILDING_ID="9552"\nROOM_ID="9632"\nDORM_NAME=""\n',encoding='utf-8')
        saved=ConfigStore(self.temp.name).load()['target']
        self.assertFalse(saved['building']);self.assertFalse(saved['room'])
    def test_stopping_during_selection_does_not_resume_on_completion(self):
        self.select(); self.ctl.start(automatic=True); self.wait(lambda:self.ctl.active)
        self.app.building_box.current(1); self.app.choose_building(); self.ctl.stop()
        self.wait(lambda:self.app.electricity.get()=='200')
        self.assertFalse(self.ctl.desired_running); self.assertFalse(self.ctl.active)
    def test_late_list_reply_after_token_edit_is_ignored(self):
        self.backend.block='old'; self.app.token.set('old'); self.app.last_token_value='old'
        self.app.load_campuses(); self.wait(self.backend.entered.is_set)
        self.app.token.set('new'); self.app.token_changed(immediate=True)
        self.backend.release.set()
        self.wait(lambda:len(self.app.campuses)==2 and not self.app.busy)
        self.assertEqual(self.app.token.get(),'new')
        self.assertFalse(self.app.flow_ready)
    def test_monitor_resumes_on_switch_and_manual_stop_survives_capture(self):
        self.select(); self.ctl.start(automatic=True); self.wait(lambda:self.ctl.active)
        self.app.room_box.current(0); self.app.choose_room()
        self.wait(lambda:self.ctl.active and str(self.ctl.monitor.room)=='100')
        self.ctl.stop(); self.ctl.vars['token_sync_enabled'].set(True); self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and not self.app.busy)
        self.assertFalse(self.ctl.active); self.assertFalse(self.ctl.desired_running)
    def test_restart_auto_monitor_waits_for_selection_restore(self):
        self.select(); self.ctl.vars['auto_start'].set(True); self.ctl.save_settings(silent=True)
        self.app.close(); app=self.make(True)
        self.wait(lambda:app.reminders.active)
        self.assertEqual(str(app.reminders.monitor.room),'101')
    def test_pages_use_single_settings_surface_and_resize_settles(self):
        root=self.app.root; root.deiconify()
        errors=[]; root.report_callback_exception=lambda *args:errors.append(str(args))
        for page in ('overview','login','mail','logs'):
            self.app.ui.show(page); root.update()
        self.app.ui.show('overview')
        for i in range(80):
            root.geometry(f'{760+(i%9)*40}x{600+(i%5)*30}'); root.update()
        self.wait(lambda:self.app.ui.content._job is None)
        count=self.app.ui.content.layout_count
        end=time.monotonic()+.35
        while time.monotonic()<end: root.update(); time.sleep(.005)
        self.assertLess(self.app.ui.content.layout_count-count,4)
        self.assertFalse(errors,errors)
        self.ctl.open(); self.assertEqual(self.app.ui.page,'mail')
        self.ctl.embedded.open(); self.assertEqual(self.app.ui.page,'login')
        self.assertFalse(self.ctl.dialog); self.assertFalse(self.ctl.embedded.dialog)

if __name__=='__main__': unittest.main(verbosity=2)
