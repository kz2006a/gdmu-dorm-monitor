from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from datetime import datetime, timedelta
from decimal import Decimal
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

OUT = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(OUT))
import gdmu_reminders as r


def moment(hour=8, minute=0, day=27):
    return datetime(2026, 10, day, hour, minute, tzinfo=r.BEIJING)


def config(security='SSL/TLS'):
    return r.SMTPConfig.from_values({
        'host': 'smtp.example.com', 'port': 465 if security == 'SSL/TLS' else 587,
        'security': security, 'username': 'sender@example.com',
        'recipients': 'one@example.com; two@example.com',
    }, 'local-test-secret')


class PlannerTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(r.parse_times('8:00，20:00 08:00'), ('08:00', '20:00'))
        for value in ('24:00', '08:99', '8am', ''):
            with self.assertRaises(ValueError):
                r.parse_times(value)
        with self.assertRaises(ValueError):
            r.Rules.from_values({'threshold_enabled': True, 'water_limit': 'nan'})
        with self.assertRaises(ValueError):
            r.Rules.from_values({'threshold_enabled': True, 'water_limit': '-1'})
        self.assertEqual(r.Rules.from_values({}).interval_minutes,30)

    def test_low_balance_repeat_and_recharge(self):
        p = r.Planner(r.Rules(electricity_limit=Decimal(20), water_limit=Decimal('1')), moment())
        info = {'electricityBalance': '20', 'waterBalance': '0'}
        reasons, keys = p.plan(info, moment())
        self.assertEqual(len(keys), 2)
        p.commit(keys, moment())
        self.assertEqual(p.plan(info, moment(9))[1], [])
        self.assertEqual(len(p.plan(info, moment(day=28))[1]), 2)
        p.plan({'electricityBalance': '50', 'waterBalance': '3'}, moment(10))
        self.assertEqual(len(p.plan(info, moment(11))[1]), 2)

    def test_missing_values_do_not_rearm_or_trigger(self):
        p = r.Planner(r.Rules(water_limit=Decimal('1')), moment())
        _, keys = p.plan({'waterBalance': '0'}, moment())
        p.commit(keys, moment())
        self.assertEqual(p.plan({'waterBalance': None}, moment(9))[1], [])
        self.assertEqual(p.plan({'waterBalance': '0'}, moment(10))[1], [])

    def test_daily_and_threshold_merge_and_persist(self):
        rules = r.Rules(('08:00', '20:00'), electricity_limit=Decimal(20))
        p = r.Planner(rules, moment())
        info = {'electricityBalance': '5'}
        reasons, keys = p.plan(info, moment())
        self.assertEqual(len(keys), 2)
        p.commit(keys, moment())
        resumed = r.Planner(rules, moment(), p.history)
        self.assertEqual(resumed.plan(info, moment())[1], [])
        self.assertEqual(resumed.plan(info, moment(20))[1], ['daily:20:00'])
        resumed.commit(['daily:20:00'], moment(20))
        self.assertNotIn('daily:20:00', resumed.plan(info, moment(20, 1))[1])

    def test_start_does_not_send_old_daily_times(self):
        p = r.Planner(r.Rules(('08:00',)), moment(12))
        self.assertEqual(p.due_daily(moment(12)), [])
        self.assertEqual(p.due_daily(moment(day=28)), ['08:00'])


class SMTPTests(unittest.TestCase):
    def test_ssl_and_starttls_and_partial_recipients(self):
        for secure in ('SSL/TLS', 'STARTTLS'):
            with self.subTest(secure=secure):
                with patch.object(r.smtplib, 'SMTP_SSL') as encrypted, patch.object(r.smtplib, 'SMTP') as upgraded:
                    ctor = encrypted if secure == 'SSL/TLS' else upgraded
                    smtp = ctor.return_value.__enter__.return_value
                    smtp.send_message.return_value = {'two@example.com': (550, b'not found')}
                    result = r.send_email(config(secure), '中文测试', '余量为 0 吨水')
                    self.assertEqual(result, {'accepted': 1, 'refused': 1})
                    smtp.login.assert_called_once_with('sender@example.com', 'local-test-secret')
                    self.assertEqual(smtp.starttls.call_count, int(secure == 'STARTTLS'))
                    msg = smtp.send_message.call_args.args[0]
                    self.assertEqual(str(msg['Subject']), '中文测试')
                    self.assertIn('0 吨水', msg.get_content())
                    self.assertNotIn('local-test-secret', msg.as_string())

    def test_invalid_config_and_error_redaction(self):
        with self.assertRaises(ValueError):
            r.SMTPConfig.from_values({'host': 'https://bad', 'username': 'x@y.com'}, 'x')
        error = r.smtplib.SMTPAuthenticationError(535, b'local-test-secret')
        self.assertNotIn('local-test-secret', r.error_text(error))


class Backend:
    def __init__(self):
        self.balance = {'electricityBalance': '5', 'waterBalance': '0'}
        self.calls = []
        self.error = None
    def query_balance(self, token, building, room):
        self.calls.append((building, room))
        if self.error:
            raise self.error
        return self.balance


class MonitorTests(unittest.TestCase):
    def test_delivery_failure_retries_without_consuming_rules(self):
        backend = Backend()
        sender = MagicMock(side_effect=[TimeoutError(), {'accepted': 2, 'refused': 0}])
        notices = []
        m = r.Monitor(backend, 'fake-token', 9552, 9632, '402', config(),
                      r.Rules(('08:00',), electricity_limit=Decimal(20)),
                      lambda *args: notices.append(args), sender=sender, clock=moment)
        m.step(moment(), 0)
        self.assertEqual(m.planner.history, {})
        m.step(moment(8, 30), 1800)
        self.assertEqual(sender.call_count, 2)
        self.assertIn('daily:08:00', m.planner.history)
        m.step(moment(8, 31), 1860)
        self.assertEqual(sender.call_count, 2)
        self.assertTrue(any(kind == 'mail' for kind, _ in notices))

    def test_stopping_and_history_across_restart(self):
        backend = Backend()
        sender = MagicMock(return_value={'accepted': 2, 'refused': 0})
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'.tmp') as folder:
            path = Path(folder) / 'history.json'
            kwargs = dict(state_path=path, sender=sender, clock=moment)
            rules = r.Rules(electricity_limit=Decimal(20))
            m = r.Monitor(backend, 'fake-token', 9552, 9632, '402', config(), rules, lambda *args: None, **kwargs)
            m.step(moment(), 0)
            m.stop()
            m.step(moment(9), 3600)
            second = r.Monitor(backend, 'fake-token', 9552, 9632, '402', config(), rules, lambda *args: None, **kwargs)
            second.step(moment(9), 3600)
            self.assertEqual(sender.call_count, 1)
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('fake-token', text)
            self.assertNotIn('local-test-secret', text)

    def test_expired_token_notifies_and_stops(self):
        backend = Backend()
        backend.error = ValueError('登录凭证已失效，请更新。')
        sender = MagicMock(return_value={'accepted': 2, 'refused': 0})
        notices = []
        m = r.Monitor(backend, 'fake-token', 9552, 9632, '402', config(),
                      r.Rules(electricity_limit=Decimal(20)), lambda *args: notices.append(args),
                      sender=sender, clock=moment)
        m.step(moment(), 0)
        self.assertTrue(m.stop_event.is_set())
        sender.assert_not_called()
        self.assertTrue(any(kind == 'token_expired' for kind, _ in notices))



if __name__ == '__main__':
    unittest.main(verbosity=2)
