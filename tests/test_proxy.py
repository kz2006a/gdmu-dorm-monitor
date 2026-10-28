from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
import gdmu_desktop as gui
import gdmu_proxy_ui as ui


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'.tmp')
        self.root=gui.tk.Tk();self.root.withdraw()
        self.app=gui.BalanceApp(self.root,config_dir=self.temp.name,auto_start=False)
        self.ctl=self.app.reminders
        self.panel=self.ctl.embedded
    def tearDown(self):
        if not self.app.closed:
            self.app.close()
        self.temp.cleanup()
    def test_default_start_never_changes_os(self):
        with patch.object(self.panel.service,'prepare') as prepare,patch.object(self.panel.service,'connect') as connect,patch.object(ui,'certificate_action') as trust:
            self.panel.startup()
            prepare.assert_not_called();connect.assert_not_called();trust.assert_not_called()
    def test_login_button_prepares_then_installs_then_confirms_connection(self):
        with patch.object(self.panel,'worker') as worker:
            self.panel.begin_login()
            self.assertEqual(worker.call_args.args[0],'准备登录')
        self.panel.busy=False
        with patch.object(ui,'certificate_trusted',return_value=False),patch.object(self.panel,'install_certificate') as install:
            self.panel.events.put(('ok','准备登录',None)); self.panel.poll()
            install.assert_called_once()
        with patch.object(self.panel,'connect') as connect:
            self.panel.events.put(('ok','安装证书',None)); self.panel.poll()
            connect.assert_called_once()
    def test_auto_login_respects_wake_preference(self):
        self.ctl.vars['wechat_auto_wake'].set(False)
        self.panel.login_requested=True;self.panel.login_automatic=True
        with patch.object(self.panel,'wake') as wake:
            self.panel.open_login_window(automatic=True)
            wake.assert_not_called()
    def test_expired_monitor_recovery_has_one_wake_owner(self):
        self.panel.service.connected=True
        self.ctl.waiting_for_token=True;self.ctl.desired_running=True
        self.ctl.vars['wechat_auto_wake'].set(True)
        with patch.object(self.panel,'open_login_window') as open_window:
            self.panel.request_login()
            open_window.assert_not_called()
        self.panel.service.connected=False
    def test_recovery_prerequisites_report_missing_opt_in_or_shortcut(self):
        self.assertIn('Token 同步',self.panel.recovery_unavailable())
        self.ctl.vars['token_sync_enabled'].set(True)
        self.assertIn('自动打开',self.panel.recovery_unavailable())
        self.ctl.vars['wechat_auto_wake'].set(True)
        self.assertIn('快捷方式',self.panel.recovery_unavailable())
        shortcut=Path(self.temp.name)/'test.lnk';shortcut.write_text('synthetic',encoding='utf-8')
        self.ctl.vars['wechat_shortcut'].set(str(shortcut))
        self.assertIn('同步未连接',self.panel.recovery_unavailable())
        self.ctl.vars['proxy_auto_start'].set(True)
        self.assertEqual(self.panel.recovery_unavailable(),'')
    def test_recovery_reconnects_once_only_with_saved_opt_in(self):
        self.panel.start_timer=None
        self.ctl.recovery={'deadline':9999999}
        self.ctl.desired_running=True
        self.ctl.vars['proxy_auto_start'].set(True)
        with patch.object(ui,'certificate_trusted',return_value=True),patch.object(self.panel,'prepare') as prepare:
            self.panel.advance_recovery();self.panel.advance_recovery()
            prepare.assert_called_once_with(connect_after=True)
        self.ctl.recovery=None
    def test_cancelled_proxy_confirmation_does_not_launch_or_connect(self):
        with patch.object(ui,'certificate_trusted',return_value=True),patch.object(ui.messagebox,'askokcancel',return_value=False),patch.object(self.panel,'prepare') as prepare:
            self.panel.connect()
            prepare.assert_not_called()
    def test_invalid_shortcut_does_not_open_file(self):
        self.ctl.vars['wechat_shortcut'].set('not-a-miniapp.exe')
        with patch.object(ui.os,'startfile') as launch:
            with self.assertRaises(ValueError):self.panel.wake()
            launch.assert_not_called()
    def test_stop_cancels_further_wake_and_waiting_does_not_mark_token_valid(self):
        self.ctl.waiting_for_token=True;self.ctl.desired_running=True
        self.ctl.vars['wechat_auto_wake'].set(True)
        self.panel.service.connected=True
        with patch.object(type(self.panel.service),'alive',new_callable=unittest.mock.PropertyMock,return_value=True),patch.object(self.panel,'wake') as wake:
            self.panel.last_route_check=time.monotonic()
            self.panel.poll()
            wake.assert_called_once()
            self.assertTrue(self.ctl.waiting_for_token)
            self.ctl.stop()
            self.panel.poll()
            wake.assert_called_once()
            self.assertEqual(self.panel.wake_deadline,0)
        # No real route was created; keep teardown from trying to read it.
        self.panel.service.connected=False


if __name__=='__main__':unittest.main(verbosity=2)
