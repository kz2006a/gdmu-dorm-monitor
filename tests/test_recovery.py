from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from pathlib import Path
import sys,time,unittest
from unittest.mock import patch,MagicMock,PropertyMock
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_workflow as wf
import gdmu_reminders as r
import gdmu_proxy_ui as proxy

class Recovery(unittest.TestCase):
    make=wf.Flow.make
    wait=wf.Flow.wait
    select=wf.Flow.select
    def setUp(self):
        wf.Flow.setUp(self)
        self.clock=[1000.0];self.ctl.recovery_clock=lambda:self.clock[0]
        self.sender=patch.object(r,'send_email',return_value={'accepted':1,'refused':0}).start()
        patch.object(r,'check_smtp_login',return_value=True).start()
        self.ctl.vars['email_enabled'].set(True)
        self.ctl.vars['token_sync_enabled'].set(True)
        for key,value in {'host':'smtp.example.com','username':'test@example.com','recipients':'to@example.com'}.items():self.ctl.vars[key].set(value)
        self.ctl.password.set('synthetic-authorization')
        self.panel=self.ctl.embedded
        self.panel.recovery_unavailable=lambda:''
        self.panel.advance_recovery=lambda:None
    def tearDown(self):
        self.panel.service.connected=False
        wf.Flow.tearDown(self)
        patch.stopall()
    def expire(self):
        self.select();self.ctl.start(automatic=True)
        self.wait(lambda:self.ctl.active and self.ctl.monitor.next_poll>0)
        self.backend.good.discard('old')
        self.ctl.monitor.next_poll=0
        self.ctl.monitor.step()
        self.wait(lambda:self.ctl.recovery is not None)
        self.sender.assert_not_called()
    def test_refresh_success_never_sends_expiry_mail(self):
        self.expire();self.ctl.begin_token_update('new')
        self.wait(lambda:self.ctl.active and self.ctl.monitor.token=='new')
        self.assertIsNone(self.ctl.recovery);self.sender.assert_not_called()
        self.assertFalse(self.ctl.waiting_for_token)
    def test_timeout_sends_once_and_stays_paused(self):
        self.expire();self.clock[0]+=301
        self.wait(lambda:self.sender.call_count==1)
        self.ctl.fail_recovery('重复超时');self.ctl.fail_recovery('重复事件')
        self.assertFalse(self.ctl.desired_running);self.assertFalse(self.ctl.waiting_for_token)
        self.assertFalse(self.ctl.active);self.assertIsNone(self.ctl.recovery)
        self.assertIn('Token 更新失败',self.sender.call_args.args[1])
        self.assertIn('监测已暂停',self.sender.call_args.args[2])
        self.assertEqual(self.sender.call_count,1)
    def test_invalid_candidate_waits_for_retry_budget(self):
        self.expire();self.ctl.begin_token_update('invalid')
        self.wait(lambda:not self.ctl.token_validation_busy)
        self.sender.assert_not_called();self.assertIsNotNone(self.ctl.recovery)
        self.clock[0]+=301;self.wait(lambda:self.sender.call_count==1)
    def test_repeated_expiry_keeps_original_deadline_and_notice_claim(self):
        self.expire();attempt=dict(self.ctl.recovery)
        self.clock[0]+=100;self.ctl.waiting_for_token=False
        self.ctl.begin_recovery()
        self.assertEqual(self.ctl.recovery,attempt)
        self.assertTrue(self.ctl.waiting_for_token);self.sender.assert_not_called()
    def test_user_stop_cancels_failure_mail_and_future_restart(self):
        self.expire();self.ctl.stop();self.clock[0]+=301
        self.ctl.fail_recovery('旧事件')
        self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and not self.app.busy)
        self.sender.assert_not_called();self.assertFalse(self.ctl.active)
        self.assertFalse(self.ctl.desired_running)
    def test_late_valid_token_after_terminal_failure_does_not_restart(self):
        self.expire();self.ctl.fail_recovery('自动重试已耗尽')
        self.wait(lambda:self.sender.call_count==1)
        self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and not self.app.busy)
        self.assertFalse(self.ctl.desired_running);self.assertFalse(self.ctl.active)
        self.assertEqual(self.sender.call_count,1)
    def test_smtp_failure_is_attempted_once_without_auto_retry(self):
        self.sender.side_effect=TimeoutError()
        self.expire();self.ctl.fail_recovery('快捷方式打开失败')
        self.wait(lambda:self.sender.call_count==1)
        self.ctl.fail_recovery('又一次错误')
        self.assertFalse(self.ctl.desired_running)
        self.assertEqual(self.sender.call_count,1)
    def test_disabled_email_never_uses_smtp(self):
        self.expire();self.ctl.vars['email_enabled'].set(False)
        self.ctl.fail_recovery('重试超时')
        self.assertFalse(self.ctl.desired_running);self.sender.assert_not_called()
    def test_prerequisites_unavailable_fail_once_and_pause(self):
        self.select();self.ctl.start(automatic=True);self.wait(lambda:self.ctl.active)
        self.panel.recovery_unavailable=lambda:'未配置有效快捷方式'
        self.backend.good.discard('old');self.ctl.monitor.next_poll=0;self.ctl.monitor.step()
        self.wait(lambda:self.sender.call_count==1)
        self.assertFalse(self.ctl.desired_running);self.assertFalse(self.ctl.active)
    def test_two_wake_attempts_exhausted_fail_once(self):
        self.expire()
        self.panel.service.connected=True;self.panel.expiry_seen=True
        self.panel.wake_count=2;self.panel.wake_deadline=1;self.panel.last_route_check=time.monotonic()
        with patch.object(type(self.panel.service),'alive',new_callable=PropertyMock,return_value=True):self.panel.poll()
        self.wait(lambda:self.sender.call_count==1)
        self.assertFalse(self.ctl.desired_running)
    def test_second_timeout_waits_for_candidate_validation_in_flight(self):
        self.expire();self.panel.service.connected=True;self.panel.expiry_seen=True
        self.panel.wake_count=2;self.panel.wake_deadline=1;self.panel.last_route_check=time.monotonic()
        self.ctl.token_validation_busy=True
        with patch.object(type(self.panel.service),'alive',new_callable=PropertyMock,return_value=True):self.panel.poll()
        self.sender.assert_not_called();self.assertIsNotNone(self.ctl.recovery)
        self.ctl.token_validation_busy=False
    def test_new_login_with_missing_room_does_not_send_token_error(self):
        self.expire();self.backend.missing=True;self.ctl.begin_token_update('new')
        self.wait(lambda:self.app.token.get()=='new' and not self.app.busy)
        self.assertIsNone(self.ctl.recovery);self.sender.assert_not_called()
        self.assertFalse(self.ctl.active)
    def test_start_preflight_expiry_uses_same_recovery_path(self):
        self.select();self.app.last_balance=None;self.backend.good.discard('old')
        self.ctl.start(automatic=True);self.wait(lambda:self.ctl.recovery is not None)
        self.sender.assert_not_called();self.ctl.begin_token_update('new')
        self.wait(lambda:self.ctl.active and self.ctl.monitor.token=='new')
        self.sender.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
