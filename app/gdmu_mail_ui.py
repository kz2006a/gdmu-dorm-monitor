"""Mail settings window and bridge between the UI and reminder worker."""
from datetime import datetime
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import gdmu_reminders as reminders
from gdmu_config import ConfigStore
from gdmu_token_sync import TokenInbox, fingerprint, fiddler_script, guard_candidate
from gdmu_proxy_ui import EmbeddedSyncUI
from gdmu_notifications import NativeNotifier

DEFAULTS = {
    'host': '', 'port': '465', 'security': 'SSL/TLS', 'username': '',
    'sender': '', 'recipients': '', 'daily_enabled': False,
    'daily_times': '08:00, 20:00', 'threshold_enabled': True,
    'electricity_limit': '20', 'water_limit': '1',
    'interval_minutes': '30', 'repeat_hours': '24',
    'remember_credentials': True, 'auto_start': False,
    'token_sync_enabled': False,
    'proxy_auto_start': False, 'wechat_auto_wake': False, 'wechat_shortcut': '',
    'wechat_close_after_token': True, 'wechat_window_title': '',
    'wechat_window_class': '', 'wechat_window_process': '',
    'email_enabled': False, 'desktop_enabled': True, 'desktop_each_query': True,
}


class ReminderController:
    def __init__(self, app, backend, config_dir=None, auto_start=True):
        self.app, self.root, self.backend = app, app.root, backend
        self.store = ConfigStore(config_dir)
        self.directory = self.store.directory
        self.config_error = ''
        try:
            loaded = self.store.load()
        except (OSError, ValueError) as exc:
            self.config_error = str(exc) if isinstance(exc, ValueError) else '无法读取软件目录中的 .env 配置文件。'
            loaded = {'options': {}, 'token': '', 'password': '', 'target': {}}
        saved = loaded['options']
        self.vars = {}
        for key, default in DEFAULTS.items():
            value = saved.get(key, default)
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(self.root, value=value if isinstance(value, bool) else default)
            else:
                self.vars[key] = tk.StringVar(self.root, value=str(value))
        self.password = tk.StringVar(self.root, value=loaded['password'])
        if loaded['token']:
            self.app.token.set(loaded['token'])
        target = loaded['target']
        self.app.building_id.set(target.get('building', ''))
        self.app.room_id.set(target.get('room', ''))
        self.saved_target = dict(target)
        if target.get('name'):
            self.app.result_room.set('上次宿舍：' + target['name'])
        self.events = queue.Queue()
        self.monitor = None
        self.generation = 0
        self.dialog = None
        self.settings_widgets = []
        self.log_widget = None
        self.logs = []
        self.notifier = NativeNotifier(self.root)
        if loaded.get('interval_adjusted'):
            self.log('旧配置的自动查询间隔已提升为 30 分钟。')
        self.test_busy = False
        self.desired_running = False
        self.pending_retarget = False
        self.preflight_busy = False
        self.manual_start_feedback = False
        self.validation_cancel = threading.Event()
        self.waiting_for_token = False
        self.expired_intent = False
        self.token_validation_busy = False
        self.token_sync_epoch = 0
        self.pending_token_resume = False
        self.recovery = None
        self.recovery_serial = 0
        self.recovery_clock = time.monotonic
        self.token_inbox = TokenInbox(self.directory, self.sync_note)
        self.last_sync_error = ''
        self.auto_timer = None
        self.embedded = EmbeddedSyncUI(self)
        self.poll_timer = self.root.after(250, self.poll)
        if self.config_error:
            self.app.reminder_status.set('配置读取失败：' + self.config_error)
            self.log(self.config_error + ' 请修正 .env 或在窗口中重新保存配置。')
        elif auto_start and self.vars['auto_start'].get():
            self.auto_timer = self.root.after(500, self.startup)
        self.app.sync_status.set('等待微信登录响应' if self.vars['token_sync_enabled'].get() else '尚未连接微信')

    @property
    def active(self):
        return self.monitor is not None and not self.monitor.stop_event.is_set()

    @property
    def startup_pending(self):
        return self.auto_timer is not None

    def cancel_startup(self):
        if self.auto_timer is not None:
            self.root.after_cancel(self.auto_timer)
            self.auto_timer = None

    def startup(self):
        self.auto_timer = None
        self.desired_running = True
        self.pending_token_resume = True
        if not self.app.token.get().strip():
            self.app.flow_ready = False
            self.app.status.set('等待微信登录后恢复宿舍。')
            self.embedded.request_login()

    def values(self):
        return {key: variable.get() for key, variable in self.vars.items()}

    def save_settings(self, silent=False, validate_auto=True):
        try:
            values = self.values()
            reminders.Rules.from_values(values)
            if validate_auto and values['auto_start']:
                if not values['remember_credentials']:
                    raise ValueError('启动后自动监测需要勾选保存凭证，以便读取 Token。')
                if not self.app.token.get().strip() and not values['proxy_auto_start']:
                    raise ValueError('请先连接微信，或开启下次自动连接微信。')
                if values['email_enabled'] and not values['desktop_enabled']:
                    reminders.SMTPConfig.from_values(values, self.password.get())
                reminders.Rules.from_values(values)
            try:
                building, room, name = self.target()
                selected = self.app.selected_target()
                target = selected or (dict(self.saved_target) if str(self.saved_target.get('building')) == str(building) and str(self.saved_target.get('room')) == str(room) else {})
                target.update(building=building, room=room, name=name)
            except ValueError:
                target = self.saved_target
            self.store.save(values, self.app.token.get().strip(), self.password.get(), target)
            self.saved_target = dict(target)
            self.config_error = ''
        except (OSError, ValueError) as exc:
            text = str(exc) if isinstance(exc, ValueError) else '无法写入软件目录的 .env，请把整个程序文件夹放到可写位置。'
            if not silent:
                self.app.feedback('设置未保存：'+text,'error')
                messagebox.showerror('保存失败', text, parent=self.dialog or self.root)
            self.log('配置保存失败：' + text)
            return False
        if not silent:
            self.app.status.set('设置已保存')
            self.app.feedback('监测设置已保存到本地。')
            self.log('设置已保存到软件目录的 .env。' + ('已保存 Token 和 SMTP 授权码。' if values['remember_credentials'] else '未保存凭证，并已清除文件中的旧凭证。'))
        return True

    def save_session(self):
        """Persist selection independently of unfinished reminder-form edits."""
        try:
            loaded = self.store.load()
            options = dict(DEFAULTS, **loaded['options'])
            options['remember_credentials'] = self.vars['remember_credentials'].get()
            target = self.app.selected_target()
            if target is None:
                target = dict(self.saved_target)
                if self.app.flow_ready:
                    building, room, name = self.target()
                    if str(target.get('building')) != str(building) or str(target.get('room')) != str(room):
                        target = {}
                    target.update(building=building, room=room, name=name)
            self.store.save(options, self.app.token.get().strip(), self.password.get(), target)
            self.saved_target = dict(target)
            return True
        except (OSError, ValueError):
            self.log('宿舍或登录状态未能保存，请检查配置文件及目录权限。')
            return False

    def sync_note(self, text):
        self.app.sync_status.set(text)
        self.log('Token 同步：' + text)

    def sync_changed(self):
        self.token_sync_epoch += 1
        self.token_validation_busy = False
        if self.vars['token_sync_enabled'].get():
            if self.expired_intent:
                self.waiting_for_token = True
                self.desired_running = True
            self.sync_note('已启用本地响应接收；请在“内置同步设置”开启接入。')
        else:
            self.vars['proxy_auto_start'].set(False)
            self.token_inbox.close()
            if self.embedded.service.connected:
                self.embedded.disconnect()
            if self.waiting_for_token:
                self.stop('已关闭 Token 同步，提醒保持暂停。')
            self.sync_note('已关闭同步，不再接收登录响应。')
        self.save_settings(silent=True, validate_auto=False)

    def generate_sync_script(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / 'Fiddler_同步片段.txt'
            path.write_text(fiddler_script(self.directory), encoding='utf-8-sig')
            self.vars['token_sync_enabled'].set(True)
            self.sync_changed()
            self.token_inbox.pulse()
            os.startfile(str(path))
            messagebox.showinfo('接入片段已生成', '在 Fiddler Classic 中打开 Rules → Customize Rules，找到 OnBeforeResponse 函数。\n\n将刚生成的片段粘贴到该函数的大括号内，保留原有代码，保存后在小程序查询一次。\n\n移动软件文件夹后，请重新生成并更新片段路径。', parent=self.dialog or self.root)
        except OSError:
            messagebox.showerror('生成失败', '请检查软件目录是否可写；也可查看软件目录中的 Fiddler 接入说明。', parent=self.dialog or self.root)

    def show_sync_help(self):
        try:
            os.startfile(str(self.directory / '内置同步说明.md'))
        except OSError:
            messagebox.showinfo('Token 同步', '打开“内置同步设置”，依次准备引擎、安装证书、开启同步。然后在微信小程序查询，等待新的登录响应。', parent=self.root)

    def pump_token_sync(self):
        if not self.vars['token_sync_enabled'].get():
            return
        try:
            self.token_inbox.pulse()
            self.token_inbox.collect()
            self.last_sync_error = ''
            if self.token_validation_busy or self.preflight_busy or self.app.busy:
                return
            candidate = self.token_inbox.take()
            if candidate is not None:
                self.begin_token_update(candidate)
        except OSError:
            if not self.last_sync_error:
                self.sync_note('同步目录不可读写，请检查软件目录权限。')
            self.last_sync_error = 'io'

    def begin_token_update(self, candidate):
        original = self.app.token.get().strip()
        if candidate == original and self.active and not self.embedded.window_closer.armed_until:
            self.sync_note('响应中的 Token 已在当前监测中使用，无需替换。')
            return
        try:
            guard_candidate(original, candidate)
        except ValueError as exc:
            self.sync_note(str(exc))
            return
        self.token_validation_busy = True
        epoch = self.token_sync_epoch
        self.sync_note('正在验证候选 Token（指纹 ' + fingerprint(candidate) + '）。')
        def validate():
            try:
                # List validation has no dependency on a default/previous dorm.
                campuses = self.backend.list_campuses(candidate)
                self.events.put((epoch, 'sync_valid', (original, candidate, campuses)))
            except Exception as exc:
                self.events.put((epoch, 'sync_error', reminders.error_text(exc)))
        threading.Thread(target=validate, daemon=True).start()

    def apply_synced_token(self, original, candidate, campuses=None):
        if not self.vars['token_sync_enabled'].get():
            return
        if self.app.token.get().strip() != original:
            self.sync_note('校验期间 Token 已手动更改，已忽略较早的候选结果。')
            return
        want_resume = self.active or self.desired_running or self.waiting_for_token
        self.cancel_startup()
        self.validation_cancel.set()
        self.generation += 1
        if self.monitor is not None:
            self.monitor.stop()
        self.preflight_busy = False
        self.pending_retarget = False
        self.waiting_for_token = False
        self.expired_intent = False
        self.desired_running = want_resume
        self.app.token.set(candidate)
        self.embedded.validated()
        self.app.last_token_value = candidate
        saved = self.save_settings(silent=True, validate_auto=False)
        text = '登录已验证，正在加载宿舍（指纹 ' + fingerprint(candidate) + '）。'
        if not saved:
            text += ' 配置未能保存，当前仅在内存中使用。'
        self.sync_note(text)
        self.lock_settings(False)
        self.pending_token_resume = want_resume
        self.app.cancel_requests()
        self.app.load_campuses(prefetched=campuses)
        if not want_resume:
            self.app.reminder_status.set('Token 已更新；提醒仍保持手动停止状态。')

    def log(self, text):
        self.logs.append(f'{reminders.now_local():%H:%M:%S}  {text}')
        self.logs = self.logs[-60:]
        if self.log_widget is not None and self.log_widget.winfo_exists():
            self.log_widget.configure(state='normal')
            self.log_widget.delete('1.0', 'end')
            self.log_widget.insert('end', '\n'.join(self.logs))
            self.log_widget.see('end')
            self.log_widget.configure(state='disabled')

    def open(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.deiconify()
            self.dialog.lift()
            return
        from gdmu_ui import build_mail_dialog
        build_mail_dialog(self)

    def rule_field(self, parent, row, title, key):
        ttk.Label(parent, text=title).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        field = ttk.Entry(parent, textvariable=self.vars[key])
        field.grid(row=row, column=1, sticky='ew', pady=4)
        self.settings_widgets.append(field)

    def remember_changed(self):
        if not self.vars['remember_credentials'].get():
            self.vars['auto_start'].set(False)

    def open_directory(self):
        try:
            os.startfile(str(self.directory))
            self.app.feedback('已请求打开软件文件夹。','info')
        except OSError:
            messagebox.showerror('无法打开', '请手动打开 EXE 所在的程序文件夹。', parent=self.dialog or self.root)

    def security_changed(self, event=None):
        current = self.vars['port'].get()
        if current in ('465', '587'):
            self.vars['port'].set('465' if self.vars['security'].get() == 'SSL/TLS' else '587')

    def lock_settings(self, locked):
        for widget in self.settings_widgets:
            if widget.winfo_exists():
                widget.configure(state='disabled' if locked else 'readonly' if isinstance(widget, ttk.Combobox) else 'normal')

    def test_email(self):
        if self.test_busy:
            return
        try:
            config = reminders.SMTPConfig.from_values(self.values(), self.password.get())
        except ValueError as exc:
            messagebox.showinfo('请检查 SMTP 设置', str(exc), parent=self.dialog or self.root)
            return
        self.test_busy = True
        if hasattr(self, 'test_button') and self.test_button.winfo_exists():
            self.test_button.configure(state='disabled')
        self.log('正在发送测试邮件…')
        self.app.feedback('正在向 SMTP 服务器提交测试邮件…','busy',0)
        def worker():
            try:
                result = reminders.send_email(config, '广东医宿舍水电｜SMTP 测试邮件',
                    f'这是一封由宿舍水电查询工具发送的测试邮件。\n时间：{reminders.now_local():%Y-%m-%d %H:%M:%S}（北京时间）\n收到此邮件说明 SMTP 配置可用于发送。')
                self.events.put((None, 'test_ok', result))
            except Exception as exc:
                self.events.put((None, 'test_error', reminders.error_text(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def test_desktop(self):
        try:
            self.notifier.prepare()
            if not self.notifier.show('广东医校园水电 · 测试通知',
                '桌面通知测试已提交。\n正式监测通知会显示所选宿舍的剩余电量、水量及低阈值警告。'):
                raise ValueError('Windows 未接受桌面通知。')
            self.log('测试通知已提交 Windows；若未弹出，请检查系统通知与免打扰设置。')
            self.app.feedback('测试通知已提交 Windows；若未显示，请检查系统通知和免打扰设置。','info')
        except (OSError,ValueError) as exc:
            self.log('桌面通知测试失败：'+str(exc))
            self.app.feedback('测试通知未提交：'+str(exc),'error')
            messagebox.showerror('桌面通知失败',str(exc),parent=self.dialog or self.root)

    def target(self):
        bi, ri = self.app.building_box.current(), self.app.room_box.current()
        if bi >= 0 and ri >= 0:
            return self.app.buildings[bi]['id'], self.app.rooms[ri]['id'], self.app.selection_name()
        try:
            building, room = int(self.app.building_id.get()), int(self.app.room_id.get())
            if building <= 0 or room <= 0:
                raise ValueError()
        except ValueError:
            raise ValueError('请先选择宿舍，或填写有效的内部楼栋、房间 ID。') from None
        saved = self.saved_target
        name = saved.get('name') if str(saved.get('building')) == str(building) and str(saved.get('room')) == str(room) else ''
        return building, room, name or f'楼栋 ID {building} / 房间 ID {room}'

    def start(self, automatic=False):
        if not automatic:
            self.manual_start_feedback=True
            self.app.feedback('正在准备监测，请等待登录与宿舍校验…','busy',0)
        self.cancel_startup()
        if self.token_validation_busy:
            self.desired_running = True
            self.app.reminder_status.set('正在校验候选 Token，完成后继续启动提醒。')
            return
        if self.active:
            self.log('提醒已在运行。如需修改设置，请先停止。')
            if not automatic:
                self.manual_start_feedback=False
                self.app.feedback('监测已在运行，无需重复开始。','info')
            return
        if self.preflight_busy:
            self.log('正在校验凭证，请稍候。')
            return
        if self.app.busy or not self.app.flow_ready:
            self.desired_running = True
            self.pending_token_resume = True
            self.app.reminder_status.set('等待宿舍查询完成后开始监测')
            return
        try:
            if self.app.busy:
                raise ValueError('请等待当前查询完成后再启动提醒。')
            token = self.app.token.get().strip()
            if not token:
                raise ValueError('请先在主窗口填写 Token。')
            values = self.values()
            config = None
            if values['email_enabled']:
                try:
                    config = reminders.SMTPConfig.from_values(values, self.password.get())
                except ValueError:
                    if not values['desktop_enabled']:
                        raise
                    self.log('邮件配置不完整，本次继续 Windows 通知监测；邮件暂不发送。')
            rules = reminders.Rules.from_values(self.values())
            building, room, name = self.target()
        except ValueError as exc:
            self.app.reminder_status.set(('自动启动未完成：' if automatic else '提醒未启动：') + str(exc))
            self.log(str(exc))
            if not automatic:
                self.manual_start_feedback=False
                self.app.feedback('监测未开始：'+str(exc),'error')
                messagebox.showinfo('请检查提醒配置', str(exc), parent=self.dialog or self.root)
            return
        if not self.save_settings(silent=True, validate_auto=False):
            self.app.reminder_status.set('配置保存失败，提醒未启动。请把程序放到可写文件夹。')
            if self.manual_start_feedback:
                self.manual_start_feedback=False
                self.app.feedback('配置保存失败，监测未开始，请检查目录权限。','error')
            return
        self.desired_running = True
        self.waiting_for_token = False
        self.pending_retarget = False
        self.preflight_busy = True
        self.generation += 1
        generation = self.generation
        cancel = threading.Event()
        self.validation_cancel = cancel
        old_monitor = self.monitor
        self.lock_settings(True)
        self.app.reminder_status.set(f'正在校验 Token'+(' 和 SMTP 登录' if config is not None else '')+f'：{name}…')
        self.log(f'准备监测 {name}，正在校验凭证。')
        desktop_enabled = self.vars['desktop_enabled'].get()
        cached = getattr(self.app, 'last_balance', None)
        def validate():
            try:
                actual_config = config
                if old_monitor is not None:
                    old_monitor.stop()
                    while old_monitor.thread and old_monitor.thread.is_alive():
                        if cancel.wait(.1):
                            return
                if cancel.is_set():
                    return
                if cached and cached[:3] == (token, str(building), str(room)) and time.monotonic()-cached[4] < 20:
                    info = cached[3]
                else:
                    info = self.backend.query_balance(token, building, room)
                if cancel.is_set():
                    return
                self.events.put((generation, 'token_recovered', None))
                if config is not None:
                    try:
                        reminders.check_smtp_login(config)
                    except Exception as exc:
                        if not desktop_enabled:
                            raise
                        actual_config = None
                        self.events.put((generation,'warning','邮件校验未通过，继续本地监测：'+reminders.error_text(exc)))
                if cancel.is_set():
                    return
                self.events.put((generation, 'validated', (token, building, room, name, actual_config, rules, info)))
            except Exception as exc:
                if not cancel.is_set():
                    self.events.put((generation, 'validation_error', (reminders.error_text(exc), automatic)))
        threading.Thread(target=validate, daemon=True).start()

    def activate(self, generation, payload):
        token, building, room, name, config, rules, info = payload
        self.preflight_busy = False
        self.waiting_for_token = False
        self.expired_intent = False
        if not self.desired_running:
            return
        self.finish_recovery()
        desktop = None
        if self.vars['desktop_enabled'].get():
            try:
                self.notifier.prepare()
                desktop = self.notifier.show
            except (OSError,ValueError) as exc:
                self.log('Windows 通知未就绪，监测仍会继续：'+str(exc))
        self.monitor = reminders.Monitor(self.backend, token, building, room, name, config, rules,
            lambda kind, data: self.events.put((generation, kind, data)),
            state_path=self.directory / 'reminder-history.json', initial_info=info,
            desktop_notify=desktop, desktop_each_query=self.vars['desktop_each_query'].get())
        self.lock_settings(True)
        self.app.reminder_status.set(f'提醒运行中：{name}；每 {rules.interval_minutes} 分钟检查。')
        self.log(f'凭证校验成功，已开始监测：{name}。固定时间使用北京时间。')
        self.monitor.start()
        if self.manual_start_feedback:
            self.manual_start_feedback=False
            self.app.feedback(f'监测已开始，每 {rules.interval_minutes} 分钟检查水电余量。')

    def stop(self, reason='提醒已停止。'):
        if self.manual_start_feedback:
            self.app.ui.clear_feedback()
        self.manual_start_feedback=False
        was_active = self.active or self.preflight_busy or self.pending_retarget or self.startup_pending or self.waiting_for_token or self.expired_intent
        self.cancel_startup()
        self.recovery = None
        self.embedded.cancel_wake()
        self.desired_running = False
        self.waiting_for_token = False
        self.expired_intent = False
        self.pending_token_resume = False
        self.pending_retarget = False
        self.preflight_busy = False
        self.validation_cancel.set()
        if self.monitor is not None:
            self.monitor.stop()
        self.generation += 1
        self.lock_settings(False)
        if was_active:
            self.app.reminder_status.set(reason)
            self.log(reason)

    def pause_for_selection(self, reason):
        if not (self.active or self.desired_running or self.preflight_busy or self.startup_pending):
            return
        self.cancel_startup()
        if self.pending_retarget and not self.active and not self.preflight_busy:
            return
        self.desired_running = True
        self.pending_retarget = True
        self.preflight_busy = False
        self.validation_cancel.set()
        if self.monitor is not None:
            self.monitor.stop()
        self.generation += 1
        self.lock_settings(False)
        text = reason + ' 选好新房间后会自动继续提醒。'
        self.app.reminder_status.set(text)
        self.log(text)

    def resume_for_selection(self):
        self.save_settings(silent=True, validate_auto=False)
        if self.desired_running and (self.pending_retarget or self.pending_token_resume):
            self.pending_token_resume = False
            self.start(automatic=True)

    def login_expired(self):
        """Allow login recovery even when the user only wants one-off queries."""
        if self.desired_running:
            self.begin_recovery()
            return
        self.expired_intent = self.desired_running
        self.waiting_for_token = self.vars['token_sync_enabled'].get() and self.desired_running
        self.app.flow_ready = False
        self.app.status.set('登录已过期，正在等待微信重新登录。')
        self.embedded.request_login()

    def begin_recovery(self):
        """One bounded silent recovery transaction per running monitoring intent."""
        if not self.desired_running:
            return
        if self.recovery is not None:
            # A list-valid candidate may still fail the final balance query.
            # Keep the same deadline/notice claim, and let login recovery continue.
            self.waiting_for_token = True
            self.pending_token_resume = False
            self.app.flow_ready = False
            return
        self.recovery_serial += 1
        try:
            name = self.target()[2]
        except ValueError:
            name = self.app.result_room.get()
        smtp = self.monitor.smtp if self.monitor is not None else None
        if smtp is None and self.vars['email_enabled'].get():
            try:
                smtp = reminders.SMTPConfig.from_values(self.values(), self.password.get())
            except ValueError:
                pass
        self.recovery = {'id': self.recovery_serial, 'deadline': self.recovery_clock()+300,
                         'smtp': smtp, 'name': name}
        if self.monitor is not None:
            self.monitor.stop()
        self.app.cancel_requests()
        self.app.flow_ready = False
        self.pending_token_resume = False
        self.pending_retarget = False
        self.waiting_for_token = True
        self.expired_intent = True
        self.embedded.cancel_wake()
        self.embedded.expiry_seen = False
        self.embedded.recovery_connect_attempted = False
        self.app.reminder_status.set('登录已过期，正在自动更新，暂不发送异常邮件。')
        self.log('Token 已过期，进入静默自动恢复（最长 5 分钟）。')
        reason = self.embedded.recovery_unavailable()
        if reason and not self.token_validation_busy:
            self.fail_recovery(reason)

    def finish_recovery(self, queried=True):
        if self.recovery is not None:
            self.log('自动更新成功，已查询宿舍余量；未发送 Token 过期邮件。' if queried else
                     '登录已更新，原宿舍不可用，等待重新选择；未发送 Token 过期邮件。')
            self.recovery = None

    def fail_recovery(self, reason):
        attempt = self.recovery
        if attempt is None or not self.desired_running:
            return
        # Claim this attempt before stopping/spawning; repeated timeout/error
        # events can no longer send a second failure notice.
        self.recovery = None
        self.embedded.window_closer.cancel()
        self.stop('自动更新登录失败，监测已暂停。请重新连接微信后手动开始监测。')
        self.app.flow_ready = False
        self.app.status.set('自动更新失败，监测已暂停：' + reason)
        self.log('静默恢复失败：' + reason)
        moment = reminders.now_local()
        body = (f'宿舍：{attempt["name"]}\n时间：{moment:%Y-%m-%d %H:%M:%S}（北京时间）\n'
                f'Token 已过期，自动更新失败：{reason}\n'
                '监测已暂停，本轮不会重复发送过期通知。请打开软件重新连接微信，再手动开始监测。')
        if self.vars['desktop_enabled'].get():
            try:
                self.notifier.prepare()
                self.notifier.show('宿舍水电 · 登录更新失败', body, True)
            except (OSError, ValueError):
                self.log('登录更新失败的桌面通知未能提交。')
        if not self.vars['email_enabled'].get() or attempt['smtp'] is None:
            self.log('未启用邮件或 SMTP 配置不可用；未发送登录失效邮件。')
            return
        def send_once():
            try:
                result = reminders.send_email(attempt['smtp'], f'宿舍水电 · Token 更新失败｜{attempt["name"]}', body)
                text = ('Token 更新失败邮件已提交 SMTP，本轮只通知一次。' if result['accepted'] > 0
                        else 'Token 更新失败邮件未被收件服务器接受；监测保持暂停，不自动重发。')
            except Exception as exc:
                text = 'Token 更新失败邮件发送未完成；监测保持暂停，不自动重发：' + reminders.error_text(exc)
            self.events.put((None, 'recovery_notice', text))
        threading.Thread(target=send_once, daemon=True).start()

    def poll(self):
        if self.app.closed:
            return
        try:
            while True:
                generation, kind, data = self.events.get_nowait()
                if kind == 'recovery_notice':
                    self.log(data)
                    continue
                if kind.startswith('test_'):
                    self.test_busy = False
                    if hasattr(self, 'test_button') and self.test_button.winfo_exists():
                        self.test_button.configure(state='normal')
                    if kind == 'test_error':
                        self.log('测试邮件失败：' + data)
                        self.app.feedback('测试邮件未提交：'+data,'error')
                    else:
                        text = f'测试邮件已提交 SMTP 服务器，接受 {data["accepted"]} 个、拒绝 {data["refused"]} 个收件人。请检查收件箱或垃圾邮件。'
                        self.log(text)
                        self.app.feedback(text,'success' if data['accepted'] and not data['refused'] else 'warning' if data['accepted'] else 'error')
                    continue
                if kind in ('sync_valid', 'sync_error'):
                    if generation != self.token_sync_epoch:
                        continue
                    self.token_validation_busy = False
                    if kind == 'sync_valid':
                        self.apply_synced_token(*data)
                    else:
                        self.sync_note('候选 Token 验证失败，保留原凭证：' + data)
                    continue
                if generation != self.generation:
                    continue
                if kind == 'validated':
                    self.activate(generation, data)
                elif kind == 'token_expired':
                    self.begin_recovery()
                elif kind == 'token_recovered':
                    self.finish_recovery()
                elif kind == 'validation_error':
                    self.preflight_busy = False
                    self.pending_retarget = False
                    self.lock_settings(False)
                    text, automatic = data
                    if '登录凭证已失效' in text:
                        self.log('凭证已过期，尝试自动更新。')
                        self.begin_recovery()
                        continue
                    if self.recovery is not None:
                        self.fail_recovery('更新后的登录或宿舍验证未完成：' + text)
                        continue
                    self.expired_intent = '登录凭证已失效' in text
                    self.waiting_for_token = self.vars['token_sync_enabled'].get() and self.expired_intent
                    self.desired_running = self.waiting_for_token
                    self.log('凭证校验失败：' + text)
                    if self.manual_start_feedback:
                        self.manual_start_feedback=False
                        self.app.feedback('监测未开始：'+text,'error')
                    self.app.reminder_status.set('Token 失效，等待小程序重新登录后自动续上提醒。' if self.waiting_for_token else '提醒已暂停：' + text)
                    if not automatic and not self.waiting_for_token:
                        messagebox.showerror('凭证校验未通过', text, parent=self.dialog or self.root)
                elif kind == 'balance':
                    info = data['info']
                    self.app.result_room.set(data['name'])
                    for variable, key in ((self.app.electricity, 'electricityBalance'), (self.app.water, 'waterBalance')):
                        value = info.get(key)
                        variable.set('未提供' if value is None or value == '' else str(value))
                    self.app.updated.set(f'自动查询成功于 {data["time"]:%Y-%m-%d %H:%M:%S}（北京时间）')
                else:
                    self.log(data)
                    self.app.reminder_status.set(data)
                    if kind == 'stopped':
                        self.expired_intent = self.desired_running and 'Token 已失效' in data
                        self.waiting_for_token = self.vars['token_sync_enabled'].get() and self.expired_intent
                        self.desired_running = self.waiting_for_token
                        self.pending_retarget = False
                        self.lock_settings(False)
                        if self.waiting_for_token:
                            self.app.reminder_status.set('Token 失效，等待微信小程序重新登录；新 Token 到达后自动继续。')
        except queue.Empty:
            pass
        self.pump_token_sync()
        self.embedded.poll()
        if self.recovery is not None and self.recovery_clock() >= self.recovery['deadline']:
            self.fail_recovery('自动更新超过 5 分钟，未能验证并恢复宿舍查询。')
        if self.pending_token_resume and self.desired_running and self.app.flow_ready and not self.app.busy and not self.preflight_busy and not self.token_validation_busy:
            self.pending_token_resume = False
            self.start(automatic=True)
        if not self.app.closed:
            self.poll_timer = self.root.after(250, self.poll)

    def close_dialog(self):
        if self.dialog is not None:
            self.dialog.destroy()
        self.dialog, self.log_widget = None, None
        self.settings_widgets = []

    def close(self):
        self.notifier.close()
        try:
            self.embedded.close()
        except (OSError, ValueError) as exc:
            messagebox.showwarning('请检查网络代理', '代理恢复未完成：' + str(exc) + '\n请在 Windows 网络设置中检查代理，或重新启动软件后使用“恢复网络”。', parent=self.root)
        self.root.after_cancel(self.poll_timer)
        self.cancel_startup()
        self.token_sync_epoch += 1
        self.token_inbox.close()
        if not self.config_error:
            self.save_settings(silent=True, validate_auto=False)
        self.stop()
        self.password.set('')
