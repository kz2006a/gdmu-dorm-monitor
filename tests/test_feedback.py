"""User-visible outcomes for manual actions, using local files and fake services."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
(ROOT/'tests/.tmp').mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'app'))
import gdmu_desktop as gui
import gdmu_mail_ui as mail
import gdmu_proxy_ui as proxy


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests/.tmp')
        self.root=gui.tk.Tk();self.root.withdraw()
        self.app=gui.BalanceApp(self.root,config_dir=self.temp.name,auto_start=False)
        self.ctl=self.app.reminders;self.panel=self.ctl.embedded
        self.ctl.vars['desktop_enabled'].set(False)
        self.ctl.vars['email_enabled'].set(False)

    def tearDown(self):
        if not self.app.closed:self.app.close()
        self.temp.cleanup()

    @property
    def feedback(self):return self.app.ui.feedback_text.get()

    def wait(self,condition):
        end=time.monotonic()+3
        while time.monotonic()<end:
            self.root.update()
            if condition():return
            time.sleep(.01)
        self.fail('Timed out waiting for the simulated action')

    def test_save_button_confirms_real_persistence_and_survives_background_status(self):
        self.app.ui.show('mail')
        self.ctl.vars['electricity_limit'].set('25')
        self.app.ui.save_button.invoke()
        self.assertEqual(self.ctl.store.load()['options']['electricity_limit'],'25')
        self.assertIn('监测设置已保存',self.feedback)
        self.app.status.set('后台查询状态')
        self.assertIn('监测设置已保存',self.feedback)
        self.assertEqual(str(self.app.ui.feedback_label.cget('textvariable')),str(self.app.ui.feedback_display))
        self.assertEqual(self.app.ui.feedback_label.cget('bg'),self.app.ui.feedback_label.master.cget('bg'))
        self.assertEqual(self.app.ui.feedback_label.winfo_manager(),'place')

    def test_failed_disk_write_never_reports_save_success(self):
        with patch.object(self.ctl.store,'save',side_effect=OSError('offline')),patch.object(mail.messagebox,'showerror'):
            self.assertFalse(self.ctl.save_settings())
        self.assertTrue(self.feedback.startswith('未完成 · 设置未保存'))

    def test_connection_save_failure_does_not_claim_window_settings_saved(self):
        with patch.object(self.ctl,'save_settings',return_value=False):
            self.assertFalse(self.panel.save())
            self.panel.automatic_window()
        self.assertIn('未保存',self.feedback)
        self.assertNotIn('已保存',self.feedback)

    def test_selecting_shortcut_confirms_the_path_was_saved(self):
        path=Path(self.temp.name)/'test.lnk';path.write_text('synthetic')
        with patch.object(proxy.filedialog,'askopenfilename',return_value=str(path)):
            self.panel.choose_shortcut()
        self.assertEqual(self.ctl.store.load()['options']['wechat_shortcut'],str(path))
        self.assertIn('快捷方式已保存',self.feedback)

    def test_network_recovery_is_visible_on_the_connection_page(self):
        self.app.ui.show('login')
        with patch.object(self.panel.service,'recover',return_value='restored'):
            self.panel.recover()
        self.assertIn('恢复检查完成',self.feedback)
        self.assertEqual(str(self.app.ui.connection_status.cget('textvariable')),str(self.panel.status))
        with patch.object(self.panel.service,'recover',return_value='changed-externally'):
            self.panel.recover()
        self.assertTrue(self.feedback.startswith('请注意'))

    def test_notification_acknowledges_submission_without_claiming_display(self):
        with patch.object(self.ctl.notifier,'prepare'),patch.object(self.ctl.notifier,'show',return_value=True):
            self.ctl.test_desktop()
        self.assertIn('已提交 Windows',self.feedback)
        self.assertNotIn('已显示',self.feedback)

    def test_test_email_waits_for_worker_and_distinguishes_all_recipients_rejected(self):
        entered=threading.Event();release=threading.Event()
        def send(*args):
            entered.set();release.wait(3)
            return {'accepted':0,'refused':1}
        with patch.object(mail.reminders.SMTPConfig,'from_values',return_value=object()),patch.object(mail.reminders,'send_email',side_effect=send):
            self.ctl.test_email()
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(self.feedback.startswith('进行中'))
                self.assertTrue(self.ctl.test_button.instate(['disabled']))
            finally:release.set()
            self.wait(lambda:not self.ctl.test_busy)
        self.assertTrue(self.feedback.startswith('未完成'))
        self.assertIn('接受 0 个',self.feedback)
        self.assertTrue(self.ctl.test_button.instate(['!disabled']))

    def test_old_expiry_callback_cannot_erase_new_feedback(self):
        self.app.ui.notify('第一个操作',duration=1)
        old=self.app.ui.feedback_serial
        self.app.ui.notify('第二个操作',duration=0)
        self.app.ui.clear_feedback(old)
        self.root.update()
        self.assertIn('第二个操作',self.feedback)
        self.app.ui.clear_feedback()
        self.app.status.set('当前流程')
        self.assertEqual(self.feedback,'')
        self.assertFalse(self.app.ui.feedback_label.winfo_manager())
        self.assertEqual(str(self.app.ui.footer_text.cget('textvariable')),str(self.app.status))

    def test_certificate_result_only_reports_completion_after_worker_finishes(self):
        self.panel.manual_feedback=True
        self.app.feedback('正在移除证书','busy',0)
        self.assertTrue(self.feedback.startswith('进行中'))
        self.panel.events.put(('ok','移除证书','已移除本目录对应的用户根证书。'))
        self.panel.poll()
        self.assertTrue(self.feedback.startswith('完成'))
        self.panel.manual_feedback=True
        self.panel.events.put(('error','移除证书','操作被取消'))
        self.panel.poll()
        self.assertTrue(self.feedback.startswith('未完成'))

    def test_clearing_an_already_empty_token_still_acknowledges_persistence(self):
        self.app.clear_token()
        self.assertIn('Token 已清除',self.feedback)
        self.assertEqual(self.ctl.store.load()['token'],'')

    def test_start_and_stop_feedback_follows_actual_monitor_state(self):
        self.app.token.set('offline')
        self.app.building_id.set('10');self.app.room_id.set('100')
        self.app.flow_ready=True
        self.app.last_balance=('offline','10','100',{'electricityBalance':'100','waterBalance':'10'},time.monotonic())
        self.app.ui.toggle_monitor()
        self.assertTrue(self.feedback.startswith('进行中'))
        self.wait(lambda:self.ctl.active)
        self.assertIn('监测已开始',self.feedback)
        self.app.ui.toggle_monitor()
        self.assertFalse(self.ctl.active)
        self.assertIn('监测已停止',self.feedback)


if __name__=='__main__':unittest.main(verbosity=2)
