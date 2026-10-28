"""SMTP delivery and daily/low-balance reminder scheduling."""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, make_msgid, parseaddr
import json
from pathlib import Path
import re
import smtplib
import ssl
import threading
import time
import urllib.error

BEIJING = timezone(timedelta(hours=8))


def now_local():
    return datetime.now(BEIJING)


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_times(text):
    result = set()
    for item in re.split(r'[,，;；\s]+', text.strip()):
        if not item:
            continue
        if not re.fullmatch(r'\d{1,2}:\d{2}', item):
            raise ValueError('提醒时间请填写 HH:MM，例如 08:00, 20:00。')
        hour, minute = map(int, item.split(':'))
        if hour > 23 or minute > 59:
            raise ValueError('提醒时间必须在 00:00 到 23:59 之间。')
        result.add(f'{hour:02d}:{minute:02d}')
    if not result:
        raise ValueError('请至少填写一个固定提醒时间。')
    return tuple(sorted(result))


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    security: str
    username: str
    password: str
    sender: str
    recipients: tuple

    @classmethod
    def from_values(cls, values, password):
        host = str(values.get('host', '')).strip()
        if not host or any(ch in host for ch in '/\\ \r\n'):
            raise ValueError('SMTP 服务器请填写主机名，例如 smtp.example.com，不要带 https://。')
        try:
            port = int(values.get('port', '465'))
        except (ValueError, TypeError):
            raise ValueError('SMTP 端口必须是整数。') from None
        if not 1 <= port <= 65535:
            raise ValueError('SMTP 端口必须在 1 到 65535 之间。')
        security = values.get('security', 'SSL/TLS')
        if security not in ('SSL/TLS', 'STARTTLS'):
            raise ValueError('请选择 SSL/TLS 或 STARTTLS。')
        username = str(values.get('username', '')).strip()
        if not username or not password:
            raise ValueError('请填写 SMTP 登录账号和密码 / 授权码。')
        sender_input = str(values.get('sender', '')).strip() or username
        recipient_input = str(values.get('recipients', '')).strip()
        if any(ch in sender_input + recipient_input + username for ch in '\r\n'):
            raise ValueError('邮箱地址和账号不能包含换行。')
        sender = parseaddr(sender_input)[1]
        recipients = tuple(dict.fromkeys(addr for _, addr in getaddresses([
            recipient_input.replace('；', ',').replace(';', ',').replace('，', ',')
        ])))
        if not valid_address(sender) or not recipients or any(not valid_address(x) for x in recipients):
            raise ValueError('请填写有效的发件人和收件人邮箱；多个收件人用逗号分隔。')
        return cls(host, port, security, username, password, sender, recipients)


def valid_address(value):
    return bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value))


@dataclass(frozen=True)
class Rules:
    daily_times: tuple = ()
    electricity_limit: object = None
    water_limit: object = None
    interval_minutes: int = 30
    repeat_hours: int = 24

    @classmethod
    def from_values(cls, values):
        daily = parse_times(str(values.get('daily_times', ''))) if values.get('daily_enabled') else ()
        limits = []
        for field, title in (('electricity_limit', '电量'), ('water_limit', '水量')):
            raw = str(values.get(field, '')).strip()
            limit = number(raw) if values.get('threshold_enabled') and raw else None
            if values.get('threshold_enabled') and raw and (limit is None or limit < 0):
                raise ValueError(f'{title}阈值必须是大于等于零的数字。')
            limits.append(limit)
        if values.get('threshold_enabled') and all(x is None for x in limits):
            raise ValueError('低余量提醒请至少填写电量或水量其中一个阈值。')
        if not daily and all(x is None for x in limits):
            raise ValueError('请启用固定时间提醒或低余量提醒。')
        try:
            interval = int(values.get('interval_minutes', 30))
            repeat = int(values.get('repeat_hours', 24))
        except (ValueError, TypeError):
            raise ValueError('查询间隔和重复提醒间隔必须是整数。') from None
        if not 5 <= interval <= 1440:
            raise ValueError('查询间隔请设置为 5 到 1440 分钟。')
        if not 1 <= repeat <= 168:
            raise ValueError('持续低余量的重复提醒间隔请设置为 1 到 168 小时。')
        return cls(daily, *limits, interval, repeat)


def error_text(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f'查询接口返回 HTTP {exc.code}，请检查登录凭证、账号权限和服务状态。'
    if isinstance(exc, urllib.error.URLError):
        return '无法连接缴费站点，请检查网络、代理与证书配置。'
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'SMTP 登录失败，请检查账号、授权码，以及邮箱是否已开启 SMTP 服务。'
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return '所有收件人均被服务器拒绝，请检查收件地址。'
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return '发件地址被服务器拒绝，请检查它是否与登录账号匹配。'
    if isinstance(exc, ssl.SSLError):
        return 'TLS 连接或证书校验失败，请检查服务器、端口和加密方式。'
    if isinstance(exc, smtplib.SMTPException):
        return 'SMTP 服务拒绝发送，请检查邮箱设置、服务状态和发送额度。'
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return '网络连接失败或超时，请检查服务器地址、端口和网络。'
    if isinstance(exc, ValueError):
        return str(exc)
    return '操作未完成，请检查设置后重试。'


@contextmanager
def authenticated_smtp(config):
    context = ssl.create_default_context()
    if config.security == 'SSL/TLS':
        connection = smtplib.SMTP_SSL(config.host, config.port, timeout=25, context=context)
    else:
        connection = smtplib.SMTP(config.host, config.port, timeout=25)
    with connection as smtp:
        if config.security == 'STARTTLS':
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(config.username, config.password)
        yield smtp


def check_smtp_login(config):
    with authenticated_smtp(config):
        return True


def send_email(config, subject, body):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = config.sender
    msg['To'] = ', '.join(config.recipients)
    msg['Date'] = format_datetime(now_local())
    msg['Message-ID'] = make_msgid()
    msg.set_content(body)
    with authenticated_smtp(config) as smtp:
        refused = smtp.send_message(msg, from_addr=config.sender, to_addrs=list(config.recipients))
    return {'accepted': len(config.recipients) - len(refused), 'refused': len(refused)}


def balance_body(name, info, reasons, moment):
    def display(key):
        value = info.get(key)
        return '未提供' if value is None or value == '' else str(value)
    return '\n'.join([
        '广东医宿舍水电提醒', '', f'宿舍：{name}',
        f'查询时间：{moment.astimezone(BEIJING):%Y-%m-%d %H:%M:%S}（北京时间）',
        f'剩余电量：{display("electricityBalance")} 度',
        f'剩余水量：{display("waterBalance")} 吨', '',
        '提醒原因：', *['• ' + reason for reason in reasons], '',
        '请根据实际情况在广东医缴费小程序中充值。',
        '以上为上游返回的读数，查询时间不等于抄表更新时间。',
    ])


class Planner:
    def __init__(self, rules, started, history=None):
        self.rules = rules
        self.history = dict(history) if isinstance(history, dict) else {}
        self.next_daily = {}
        for value in rules.daily_times:
            hour, minute = map(int, value.split(':'))
            candidate = started.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate < started.replace(second=0, microsecond=0):
                candidate += timedelta(days=1)
            self.next_daily[value] = candidate

    def due_daily(self, moment):
        return [key for key, scheduled in self.next_daily.items() if moment >= scheduled]

    def plan(self, info, moment):
        reasons, keys = [], []
        daily = self.due_daily(moment)
        for key in daily:
            stamp = f'daily:{key}'
            scheduled = self.next_daily[key]
            while scheduled + timedelta(days=1) <= moment:
                scheduled += timedelta(days=1)
            self.next_daily[key] = scheduled
            if self.history.get(stamp) != scheduled.date().isoformat():
                reasons.append(f'每日 {key} 定时提醒')
                keys.append(stamp)
            else:
                while self.next_daily[key] <= moment:
                    self.next_daily[key] += timedelta(days=1)
        for field, limit, title, unit in (
            ('electricityBalance', self.rules.electricity_limit, '电量', '度'),
            ('waterBalance', self.rules.water_limit, '水量', '吨'),
        ):
            if limit is None:
                continue
            value = number(info.get(field))
            if value is None:
                continue
            stamp = f'low:{field}:{limit}'
            if value > limit:
                self.history.pop(stamp, None)
                continue
            last = self.history.get(stamp)
            try:
                elapsed = moment - datetime.fromisoformat(last) if last else None
            except (ValueError, TypeError):
                elapsed = None
            if elapsed is None or elapsed >= timedelta(hours=self.rules.repeat_hours):
                reasons.append(f'{title}为 {value} {unit}，不高于设置的 {limit} {unit}')
                keys.append(stamp)
        return reasons, keys

    def commit(self, keys, moment):
        for key in keys:
            if key.startswith('daily:'):
                value = key[6:]
                self.history[key] = self.next_daily[value].date().isoformat()
                while self.next_daily[value] <= moment:
                    self.next_daily[value] += timedelta(days=1)
            else:
                self.history[key] = moment.isoformat()


def load_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class Monitor:
    def __init__(self, backend, token, building, room, name, smtp, rules, notify,
                 state_path=None, sender=None, clock=now_local, initial_info=None):
        self.backend, self.token = backend, token
        self.building, self.room, self.name = building, room, name
        self.smtp, self.rules, self.notify = smtp, rules, notify
        self.state_path, self.sender, self.clock = state_path, sender or send_email, clock
        self.initial_info = initial_info
        self.stop_event = threading.Event()
        histories = load_json(state_path) if state_path else {}
        self.dorm_key = f'{building}:{room}'
        self.histories = histories
        self.planner = Planner(rules, clock(), histories.get(self.dorm_key))
        self.next_poll = 0.0
        self.retry_after = 0.0
        self.failures = 0
        self.last_failure_notice = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def save_state(self):
        if self.state_path:
            self.histories[self.dorm_key] = self.planner.history
            try:
                save_json(self.state_path, self.histories)
            except OSError:
                self.notify('warning', '提醒去重记录保存失败；重启后可能再次提醒。')

    def step(self, moment=None, monotonic=None):
        moment = moment or self.clock()
        monotonic = time.monotonic() if monotonic is None else monotonic
        if self.stop_event.is_set() or monotonic < self.retry_after:
            return
        if monotonic < self.next_poll and not self.planner.due_daily(moment):
            return
        self.next_poll = monotonic + self.rules.interval_minutes * 60
        try:
            if self.initial_info is not None:
                info, self.initial_info = self.initial_info, None
            else:
                info = self.backend.query_balance(self.token, self.building, self.room)
            if self.stop_event.is_set():
                return
            self.failures = 0
            self.notify('balance', {'info': info, 'time': moment, 'name': self.name})
        except Exception as exc:
            self.failures += 1
            self.retry_after = monotonic + 60
            self.next_poll = monotonic + 60
            text = error_text(exc)
            self.notify('error', '余量查询失败：' + text)
            expired = isinstance(exc, ValueError) and '登录凭证已失效' in str(exc)
            if expired or self.failures >= 3:
                self.failure_notice(text, moment)
            if expired:
                self.stop_event.set()
                self.notify('stopped', 'Token 已失效，提醒已停止。请更新 Token 后重新启动。')
            return
        reasons, keys = self.planner.plan(info, moment)
        # Persist recovery even when a simultaneous daily email fails.
        self.save_state()
        if not reasons:
            self.notify('checked', '余量已更新，目前没有需要发送的提醒。')
            return
        if self.stop_event.is_set():
            return
        try:
            result = self.sender(self.smtp, f'宿舍水电提醒｜{self.name}', balance_body(self.name, info, reasons, moment))
            if result['accepted'] <= 0:
                raise ValueError('邮件未被任何收件人的服务器接受。')
            self.planner.commit(keys, moment)
            self.save_state()
            text = '提醒邮件已提交 SMTP 服务器。'
            if result['refused']:
                text += f' 有 {result["refused"]} 个收件人被拒绝，请检查地址。'
            self.notify('mail', text)
        except Exception as exc:
            # Do not consume reminders on failed delivery. Retry with fresh data.
            self.retry_after = monotonic + 60
            self.next_poll = monotonic + 60
            self.notify('error', '邮件发送失败，将在约 1 分钟后重试：' + error_text(exc))

    def failure_notice(self, text, moment):
        if self.stop_event.is_set():
            return
        if self.last_failure_notice and moment - self.last_failure_notice < timedelta(hours=6):
            return
        try:
            result = self.sender(self.smtp, f'宿舍水电监测异常｜{self.name}',
                                 f'宿舍：{self.name}\n时间：{moment:%Y-%m-%d %H:%M:%S}（北京时间）\n'
                                 f'无法更新余量：{text}\n请打开查询工具检查网络或更新 Token。')
            if result['accepted']:
                self.last_failure_notice = moment
                self.notify('warning', '监测异常通知已提交 SMTP 服务器。')
        except Exception as exc:
            self.notify('error', '异常通知也未能发送：' + error_text(exc))

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.step()
            except Exception:
                self.notify('error', '监测遇到异常，请检查配置或重新启动提醒。')
                self.retry_after = time.monotonic() + 60
            self.stop_event.wait(3)
