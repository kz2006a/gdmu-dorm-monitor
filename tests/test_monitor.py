from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from pathlib import Path
from datetime import datetime,timedelta
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
import gdmu_reminders as r
import gdmu_desktop as gui
import gdmu_config as cfg
import gdmu_notifications as n

NOW=datetime(2026,10,28,8,0,tzinfo=r.BEIJING)

class Backend:
    def __init__(self):self.calls=[];self.fail=False;self.info={'electricityBalance':'133','waterBalance':'13.01'}
    def query_balance(self,*args):
        self.calls.append(args)
        if self.fail:raise ConnectionError('offline')
        return self.info

class MonitorTests(unittest.TestCase):
    def monitor(self,backend=None,smtp=None,rules=None,sender=None,path=None):
        self.backend=backend or Backend();self.desktop=[];self.events=[]
        def desktop(title,body,warning):self.desktop.append((title,body,warning));return True
        return r.Monitor(self.backend,'fake',9552,9632,'测试宿舍',smtp,rules or r.Rules(interval_minutes=30),
                         lambda k,d:self.events.append((k,d)),sender=sender,state_path=path,clock=lambda:NOW,desktop_notify=desktop)
    def test_no_smtp_monitor_every_30_minutes(self):
        sender=MagicMock(side_effect=AssertionError('SMTP must not be used'))
        m=self.monitor(sender=sender);m.step(NOW,0);m.step(NOW+timedelta(minutes=29),1740)
        self.assertEqual(len(self.backend.calls),1);self.assertEqual(len(self.desktop),1)
        self.assertIn('133',self.desktop[0][1]);self.assertIn('13.01',self.desktop[0][1])
        m.step(NOW+timedelta(minutes=30),1800)
        self.assertEqual(len(self.backend.calls),2);sender.assert_not_called()
    def test_threshold_upgrades_single_notice_and_recharge_rearms(self):
        self.backend=Backend();self.backend.info={'electricityBalance':'10','waterBalance':'0.5'}
        m=self.monitor(self.backend,rules=r.Rules(electricity_limit=r.number(20),water_limit=r.number(1)))
        m.step(NOW,0);self.assertEqual(len(self.desktop),1);self.assertTrue(self.desktop[0][2])
        m.step(NOW+timedelta(minutes=30),1800);self.assertFalse(self.desktop[-1][2])
        self.backend.info={'electricityBalance':'100','waterBalance':'10'};m.step(NOW+timedelta(hours=1),3600)
        self.backend.info={'electricityBalance':'1','waterBalance':'0'};m.step(NOW+timedelta(minutes=90),5400)
        self.assertTrue(self.desktop[-1][2])
    def test_email_failure_does_not_repeat_desktop_warning_or_poll_early(self):
        b=Backend();b.info={'electricityBalance':'1','waterBalance':'0'}
        sender=MagicMock(side_effect=OSError('offline'))
        m=self.monitor(b,object(),r.Rules(electricity_limit=r.number(20)),sender)
        m.step(NOW,0);m.step(NOW+timedelta(minutes=1),60)
        self.assertEqual(len(b.calls),1);self.assertEqual(len(self.desktop),1)
        m.step(NOW+timedelta(minutes=30),1800)
        self.assertEqual(sender.call_count,2);self.assertFalse(self.desktop[-1][2])
    def test_daily_between_polls_uses_last_reading_without_query(self):
        m=self.monitor(rules=r.Rules(daily_times=('08:10',)))
        m.step(NOW,0);m.step(NOW+timedelta(minutes=10),600)
        self.assertEqual(len(self.backend.calls),1);self.assertEqual(len(self.desktop),2)
        self.assertIn('08:00',self.desktop[-1][1])
    def test_network_retries_at_least_30_minutes(self):
        b=Backend();b.fail=True;m=self.monitor(b)
        for minute in (0,1,29,30,31,60):m.step(NOW+timedelta(minutes=minute),minute*60)
        self.assertEqual(len(b.calls),3)
    def test_desktop_threshold_history_survives_restart(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'.tmp') as folder:
            b=Backend();b.info={'electricityBalance':'1','waterBalance':'1'}
            path=Path(folder)/'history.json';rules=r.Rules(electricity_limit=r.number(20))
            m=self.monitor(b,rules=rules,path=path);m.step(NOW,0)
            other=self.monitor(b,rules=rules,path=path);other.step(NOW+timedelta(minutes=30),0)
            self.assertFalse(self.desktop[0][2])
    def test_rule_minimum_and_monitor_only(self):
        for interval in ('5','29'):
            with self.assertRaises(ValueError):r.Rules.from_values({'interval_minutes':interval})
        self.assertEqual(r.Rules.from_values({'interval_minutes':'30'}).interval_minutes,30)
    def test_notification_struct_and_unicode_limits(self):
        import ctypes
        self.assertEqual(ctypes.sizeof(n.NotifyIconData),976)
        self.assertLessEqual(len(n.short('通知😀'*100,63).encode('utf-16-le')),126)

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'.tmp')
        self.root=gui.tk.Tk();self.root.withdraw();self.backend=Backend()
        self.native=patch('gdmu_mail_ui.NativeNotifier',autospec=True).start()
        self.native.return_value.show.return_value=True
        self.smtp=patch.object(r,'check_smtp_login',side_effect=AssertionError('unexpected SMTP')).start()
        self.app=gui.BalanceApp(self.root,self.backend,config_dir=self.temp.name,auto_start=False)
        self.app.token.set('offline-only-token');self.ctl=self.app.reminders
        self.app.building_id.set('9552');self.app.room_id.set('9632');self.app.flow_ready=True
    def tearDown(self):
        self.app.close();patch.stopall();self.temp.cleanup()
    def wait(self,condition):
        import time
        end=time.monotonic()+4
        while time.monotonic()<end:
            self.root.update()
            if condition():return
            time.sleep(.01)
        self.fail(self.app.reminder_status.get())
    def test_blank_email_starts_and_saves_auto_start(self):
        self.ctl.vars['auto_start'].set(True)
        self.assertTrue(self.ctl.save_settings(silent=True))
        self.ctl.start(automatic=True);self.wait(lambda:self.ctl.active)
        self.smtp.assert_not_called();self.assertIsNone(self.ctl.monitor.smtp)
        self.wait(lambda:self.native.return_value.show.called)
    def test_disabled_channels_still_monitor(self):
        for key in ('desktop_enabled','email_enabled','daily_enabled','threshold_enabled'):self.ctl.vars[key].set(False)
        self.ctl.start(automatic=True);self.wait(lambda:self.ctl.active)
        self.smtp.assert_not_called();self.assertIsNone(self.ctl.monitor.desktop_notify)
    def test_old_interval_is_migrated_and_email_preserved(self):
        path=Path(self.temp.name)/'old.env'
        path.write_text('QUERY_INTERVAL_MINUTES="5"\nSMTP_HOST="smtp.example.com"\nSMTP_USERNAME="a@example.com"\nSMTP_RECIPIENTS="b@example.com"\n')
        store=cfg.ConfigStore(self.temp.name);store.path=path
        loaded=store.load();self.assertEqual(loaded['options']['interval_minutes'],'30')
        self.assertTrue(loaded['interval_adjusted']);self.assertTrue(loaded['options']['email_enabled'])
    def test_failed_smtp_does_not_stop_desktop_monitor(self):
        self.ctl.vars['email_enabled'].set(True)
        for key,value in {'host':'smtp.example.com','username':'a@example.com','recipients':'b@example.com'}.items():self.ctl.vars[key].set(value)
        self.ctl.password.set('fake-password');self.smtp.side_effect=OSError('offline')
        self.ctl.start(automatic=True);self.wait(lambda:self.ctl.active)
        self.assertIsNone(self.ctl.monitor.smtp);self.assertIsNotNone(self.ctl.monitor.desktop_notify)

if __name__=='__main__':unittest.main(verbosity=2)
