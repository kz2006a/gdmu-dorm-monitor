"""Offline release smoke test, run only with an explicit launcher argument."""
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import tkinter as tk
import gdmu_balance as api
import gdmu_config as config
import gdmu_desktop as gui
import gdmu_reminders as reminders


def run(report_path):
    report = {'passed': False, 'checks': [], 'app_loaded_from': str(Path(gui.__file__).resolve())}
    apps = []
    old_check, old_send = reminders.check_smtp_login, reminders.send_email
    checks = []
    reminders.check_smtp_login = lambda smtp: checks.append('login') or True
    reminders.send_email = lambda *args: {'accepted': 1, 'refused': 0}
    try:
        assert config.software_directory() == Path(__import__('sys').executable).resolve().parent
        assert Path(gui.__file__).resolve().parent.name == 'app'
        assert api.encrypt_json({'buildingId': 1, 'roomId': 1}) == api.SAMPLE_PARAM
        assert api.decrypt_json(api.SAMPLE_INFO)['electricityBalance'] == '100'
        report['checks'].append('External app modules, bundled crypto and adjacent config path')
        class Backend:
            def __init__(self):
                self.tokens = {'offline-token'}
            def query_balance(self, token, building, room):
                if token not in self.tokens:
                    raise ValueError('登录凭证已失效，请更新。')
                return {'electricityBalance': '133' if int(room) == 9632 else '88', 'waterBalance': '13.01'}
        def wait(app, condition):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                app.root.update()
                if condition():
                    return
                time.sleep(.01)
            raise AssertionError('Timed out: ' + app.reminder_status.get())
        with tempfile.TemporaryDirectory(dir=Path(report_path).resolve().parent) as folder:
            root = tk.Tk(); root.withdraw()
            first = gui.BalanceApp(root, Backend(), config_dir=folder, auto_start=False)
            apps.append(first)
            ctl = first.reminders
            ctl.vars['email_enabled'].set(True)
            ctl.vars['desktop_enabled'].set(False)
            first.token.set('offline-token')
            ctl.password.set('offline-password')
            for key, value in {'host': 'smtp.example.com', 'username': 'sender@example.com',
                               'recipients': 'recipient@example.com', 'auto_start': True}.items():
                ctl.vars[key].set(value)
            assert ctl.save_settings(silent=True)
            first.close()
            root = tk.Tk(); root.withdraw()
            second = gui.BalanceApp(root, Backend(), config_dir=folder, auto_start=True)
            apps.append(second)
            assert second.token.get() == 'offline-token'
            assert second.reminders.password.get() == 'offline-password'
            wait(second, lambda: second.reminders.active and second.electricity.get() == '133')
            assert checks == ['login']
            report['checks'].append('Saved credentials reload and automatic start after validation')
            second.campuses = [{'id': 1, 'name': '东莞'}]
            second.buildings = [{'id': 9552, 'name': '7栋'}]
            second.rooms = [{'id': 9632, 'name': '402'}, {'id': 9633, 'name': '403'}]
            for box, labels in zip(second.combos, [('东莞',), ('7栋',), ('402', '403')]):
                box.configure(values=labels, state='readonly'); box.current(0)
            second.room_box.current(1); second.choose_room()
            wait(second, lambda: second.reminders.active and second.reminders.monitor.room == 9633 and second.electricity.get() == '88')
            report['checks'].append('Live dorm target switching without restarting the window')
            second.reminders.vars['token_sync_enabled'].set(True)
            second.reminders.sync_changed()
            second.reminders.backend.tokens = {'new-offline-token'}
            second.reminders.monitor.next_poll = 0
            wait(second, lambda: second.reminders.waiting_for_token)
            inbox = Path(folder) / 'token-sync'
            from gdmu_wechat_window import CloseAfterToken, Window, WindowsDesktop
            from ctypes import wintypes as wt
            desktop = WindowsDesktop()
            desktop.user.GetAncestor.argtypes = [wt.HWND, wt.UINT]
            desktop.user.GetAncestor.restype = wt.HWND
            own_handle = desktop.user.GetAncestor(second.root.winfo_id(), 2)
            assert desktop.get(own_handle).pid == os.getpid()
            class TestDesktop:
                def __init__(self):
                    self.target = Window(100, 20, 12345, r'C:\ControlledTest\WeChatAppEx.exe', 'test-window', '广东医缴费')
                    self.closed = False
                def windows(self): return [self.target] if self.target else []
                def get(self, hwnd): return self.target
                def close(self, target):
                    self.closed = True
                    self.target = None
                    return True
            window_clock = [10]
            test_desktop = TestDesktop()
            closer = CloseAfterToken(second.reminders.values, second.reminders.embedded.note, test_desktop, lambda: window_clock[0])
            second.reminders.embedded.window_closer = closer
            closer.armed()
            ticks = int((time.time() + 62135596800) * 10000000)
            captured = inbox / f'{ticks}-{os.urandom(16).hex()}.login.json'
            captured.write_text(json.dumps({'ret_code': '00', 'info': api.encrypt_json({'token': 'new-offline-token'})}), encoding='utf-8')
            wait(second, lambda: second.reminders.active and second.reminders.monitor.token == 'new-offline-token')
            assert config.ConfigStore(folder).load()['token'] == 'new-offline-token'
            assert not list(inbox.glob('*.login.json'))
            assert closer.close_at == 13 and not test_desktop.closed
            window_clock[0] = 13
            closer.poll()
            assert test_desktop.closed
            report['checks'].append('Bundled Win32 window identity inspection; verified Token schedules only tracked test window close after 3 seconds')
            report['checks'].append('Expired token -> encrypted login response -> validated replacement -> automatic resume')
            second.reminders.open(); second.reminders.dialog.withdraw()
            second.root.update_idletasks()
            second.reminders.close_dialog()
            second.reminders.embedded.open()
            second.reminders.embedded.dialog.withdraw()
            second.root.update_idletasks()
            assert second.reminders.embedded.dialog.winfo_exists()
            second.reminders.embedded.dialog.destroy()
            second.reminders.embedded.dialog = None
            second.close()
            report['checks'].append('SMTP/preferences and embedded HTTPS settings windows')
        with tempfile.TemporaryDirectory(dir=Path(report_path).resolve().parent) as folder:
            class FakeNotifier:
                def __init__(self):self.calls=[]
                def prepare(self):pass
                def show(self,*args):self.calls.append(args);return True
                def close(self):pass
            before=len(checks)
            root=tk.Tk();root.withdraw()
            local=gui.BalanceApp(root,Backend(),config_dir=folder,auto_start=False);apps.append(local)
            local.reminders.notifier=FakeNotifier()
            local.token.set('offline-token');local.reminders.vars['auto_start'].set(True)
            assert local.reminders.save_settings(silent=True)
            local.reminders.start(automatic=True)
            wait(local,lambda:local.reminders.active and local.reminders.notifier.calls)
            assert local.reminders.monitor.smtp is None and len(checks)==before
            assert local.reminders.monitor.next_poll>time.monotonic()+1750
            local.close()
            root=tk.Tk();root.withdraw()
            restarted=gui.BalanceApp(root,Backend(),config_dir=folder,auto_start=True);apps.append(restarted)
            restarted.reminders.notifier=FakeNotifier()
            wait(restarted,lambda:restarted.reminders.active and restarted.reminders.notifier.calls)
            assert len(checks)==before
            restarted.close()
            report['checks'].append('No SMTP credentials: starts, desktop delivery callback, minimum 30-minute poll, restart autostart without SMTP')
        if '--with-proxy-engine' in __import__('sys').argv:
            import shutil
            from gdmu_proxy import ProxyService, certificate_thumbprint
            release = config.software_directory()
            with tempfile.TemporaryDirectory(dir=Path(report_path).resolve().parent) as folder:
                folder = Path(folder)
                (folder / 'app').mkdir()
                (folder / 'runtime/https').mkdir(parents=True)
                for name in ('gdmu_proxy.py', 'gdmu_proxy_addon.py'):
                    shutil.copy2(release / 'app' / name, folder / 'app' / name)
                shutil.copy2(release / 'runtime/https/mitmdump.exe', folder / 'runtime/https/mitmdump.exe')
                service = ProxyService(folder)
                try:
                    service.prepare()
                    assert service.alive
                    assert len(certificate_thumbprint(folder)) == 40
                    assert not service.lease.exists()
                finally:
                    service.shutdown()
                report['checks'].append('Frozen launcher starts bundled independent TLS engine; reads certificate with bundled x509; no trust or proxy mutation')
        report['passed'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    finally:
        for app in apps:
            if not app.closed:
                app.close()
        reminders.check_smtp_login, reminders.send_email = old_check, old_send
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
