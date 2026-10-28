"""Offline smoke test for the portable launcher, using synthetic data only."""
import json
import tempfile
import time
import traceback
from pathlib import Path
import tkinter as tk
import gdmu_balance as api
import gdmu_config as config
from gdmu_desktop import BalanceApp


def run(report_path):
    report={'passed':False,'checks':[]}
    apps=[]
    class Backend:
        def __init__(self):self.good={'offline-token','fresh-token'}
        def check(self,t):
            if t not in self.good:raise ValueError('登录凭证已失效，请更新。')
        def list_campuses(self,t):self.check(t);return [{'id':1,'name':'测试校区'}]
        def list_buildings(self,t,c):self.check(t);return [{'id':10,'name':'测试楼栋'}]
        def list_rooms(self,t,c,b):self.check(t);return [{'id':100,'name':'101'},{'id':101,'name':'102'}]
        def query_balance(self,t,b,r):self.check(t);return {'electricityBalance':str(r),'waterBalance':'8.5'}
    class Notifier:
        def __init__(self):self.calls=[]
        def prepare(self):pass
        def show(self,*args):self.calls.append(args);return True
        def close(self):pass
    def wait(app,condition):
        end=time.monotonic()+8
        while time.monotonic()<end:
            app.root.update()
            if condition():return
            time.sleep(.01)
        raise AssertionError(app.status.get()+' / '+app.reminder_status.get())
    try:
        assert config.software_directory()==Path(__import__('sys').executable).resolve().parent
        assert api.decrypt_json(api.SAMPLE_INFO)['electricityBalance']=='100'
        report['checks'].append('External app modules and bundled crypto')
        backend=Backend()
        with tempfile.TemporaryDirectory(dir=Path(report_path).resolve().parent) as folder:
            def make(automatic):
                root=tk.Tk();root.withdraw();a=BalanceApp(root,backend,config_dir=folder,auto_start=automatic);apps.append(a)
                a.reminders.notifier=Notifier();return a
            app=make(False)
            assert not app.building_id.get()
            app.reminders.vars['token_sync_enabled'].set(True)
            app.reminders.begin_token_update('offline-token')
            wait(app,lambda:len(app.rooms)==2 and not app.busy)
            app.room_box.current(1);app.choose_room()
            wait(app,lambda:app.electricity.get()=='101')
            saved=config.ConfigStore(folder).load()['target']
            assert (saved['campus'],saved['building'],saved['room'])==('1','10','101')
            report['checks'].append('First login without a default dorm; auto lists, selection, save and query')
            app.reminders.vars['auto_start'].set(True)
            assert app.reminders.save_settings(silent=True)
            app.close();app=make(True)
            wait(app,lambda:app.reminders.active and app.reminders.notifier.calls)
            assert str(app.reminders.monitor.room)=='101'
            assert app.reminders.monitor.smtp is None
            assert app.reminders.monitor.next_poll>time.monotonic()+1750
            report['checks'].append('Restart exact ID restoration and optional email-free autostart; >=30 minute polling')
            app.room_box.current(0);app.choose_room()
            wait(app,lambda:app.reminders.active and str(app.reminders.monitor.room)=='100')
            app.reminders.embedded.recovery_unavailable=lambda: ''
            app.reminders.embedded.advance_recovery=lambda: None
            backend.good={'fresh-token'}
            app.reminders.monitor.next_poll=0
            wait(app,lambda:app.reminders.waiting_for_token)
            inbox=Path(folder)/'token-sync';inbox.mkdir(exist_ok=True)
            (inbox/'638000000000000000-00000000000000000000000000000001.login.json').write_text(json.dumps({'ret_code':'00','info':api.encrypt_json({'token':'fresh-token'})}),encoding='utf-8')
            wait(app,lambda:app.reminders.active and app.reminders.monitor.token=='fresh-token')
            assert str(app.reminders.monitor.room)=='100'
            report['checks'].append('Live room switching and expired login response -> lists -> selected room -> monitor resume')
            # Exercise the terminal recovery transition without real email/OS changes.
            app.reminders.begin_recovery()
            assert app.reminders.recovery is not None
            app.reminders.fail_recovery('offline simulated timeout')
            app.reminders.fail_recovery('duplicate offline timeout')
            assert not app.reminders.desired_running and not app.reminders.active
            assert app.reminders.recovery is None
            report['checks'].append('Silent expiry recovery; terminal failure pauses once and cancels further monitoring')
            app.reminders.stop();app.reminders.open();assert app.ui.page=='mail'
            app.reminders.embedded.open();assert app.ui.page=='login'
            app.ui.show('overview');app.root.deiconify()
            for i in range(20):
                app.root.geometry(f'{760+i%5*45}x{600+i%3*40}');app.root.update()
            app.close()
            report['checks'].append('Single settings surfaces, native layout and clean shutdown')
        if '--with-proxy-engine' in __import__('sys').argv:
            import shutil
            from gdmu_proxy import ProxyService,certificate_thumbprint
            release=config.software_directory()
            with tempfile.TemporaryDirectory(dir=Path(report_path).resolve().parent) as folder:
                folder=Path(folder);(folder/'app').mkdir();(folder/'runtime/https').mkdir(parents=True)
                for name in ('gdmu_proxy.py','gdmu_proxy_addon.py'):shutil.copy2(release/'app'/name,folder/'app'/name)
                shutil.copy2(release/'runtime/https/mitmdump.exe',folder/'runtime/https/mitmdump.exe')
                service=ProxyService(folder)
                try:
                    service.prepare();assert service.alive
                    assert len(certificate_thumbprint(folder))==40
                    assert not service.lease.exists()
                finally:service.shutdown()
            report['checks'].append('Bundled HTTPS engine prepares and exits without changing trust/proxy')
        report['passed']=True
    except BaseException:report['error']=traceback.format_exc()
    finally:
        for app in apps:
            if not app.closed:app.close()
        Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
