"""Portable, non-executable .env configuration stored beside the launcher."""
import json
from pathlib import Path
import sys

VERSION = '1.7.1'
FIELDS = {
    'host': 'SMTP_HOST', 'port': 'SMTP_PORT', 'security': 'SMTP_SECURITY',
    'username': 'SMTP_USERNAME', 'sender': 'SMTP_SENDER', 'recipients': 'SMTP_RECIPIENTS',
    'daily_enabled': 'DAILY_ENABLED', 'daily_times': 'DAILY_TIMES',
    'threshold_enabled': 'THRESHOLD_ENABLED', 'electricity_limit': 'ELECTRICITY_LIMIT',
    'water_limit': 'WATER_LIMIT', 'interval_minutes': 'QUERY_INTERVAL_MINUTES',
    'repeat_hours': 'LOW_BALANCE_REPEAT_HOURS', 'remember_credentials': 'REMEMBER_CREDENTIALS',
    'auto_start': 'AUTO_START',
    'token_sync_enabled': 'TOKEN_SYNC_ENABLED',
    'proxy_auto_start': 'PROXY_AUTO_START', 'wechat_auto_wake': 'WECHAT_AUTO_WAKE',
    'wechat_shortcut': 'WECHAT_SHORTCUT',
    'wechat_close_after_token': 'WECHAT_CLOSE_AFTER_TOKEN',
    'wechat_window_title': 'WECHAT_WINDOW_TITLE', 'wechat_window_class': 'WECHAT_WINDOW_CLASS',
    'wechat_window_process': 'WECHAT_WINDOW_PROCESS',
    'email_enabled': 'EMAIL_ENABLED', 'desktop_enabled': 'DESKTOP_ENABLED',
    'desktop_each_query': 'DESKTOP_EACH_QUERY',
}
BOOLS = {'daily_enabled', 'threshold_enabled', 'remember_credentials', 'auto_start', 'token_sync_enabled', 'proxy_auto_start', 'wechat_auto_wake', 'wechat_close_after_token', 'email_enabled', 'desktop_enabled', 'desktop_each_query'}


def software_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def read_env(path):
    values = {}
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return values
    for index, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'.env 第 {index} 行缺少等号。')
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not key or not key.replace('_', '').isalnum():
            raise ValueError(f'.env 第 {index} 行的变量名无效。')
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                raise ValueError(f'.env 第 {index} 行的双引号或转义格式有误。') from None
            if not isinstance(value, str):
                raise ValueError(f'.env 第 {index} 行必须填写字符串。')
        elif value.startswith("'"):
            if len(value) < 2 or not value.endswith("'"):
                raise ValueError(f'.env 第 {index} 行的单引号未闭合。')
            value = value[1:-1]
        values[key] = value
    return values


class ConfigStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else software_directory()
        self.path = self.directory / '.env'

    def load(self):
        raw = read_env(self.path)
        options = {}
        for field, key in FIELDS.items():
            if key in raw:
                if field in BOOLS:
                    value = raw[key].lower()
                    if value not in ('true', 'false', '1', '0', 'yes', 'no'):
                        raise ValueError(f'.env 中 {key} 需要填写 true 或 false。')
                    options[field] = value in ('true', '1', 'yes')
                else:
                    options[field] = raw[key]
        if 'email_enabled' not in options:
            options['email_enabled'] = bool(raw.get('SMTP_HOST','').strip() and raw.get('SMTP_USERNAME','').strip() and raw.get('SMTP_RECIPIENTS','').strip())
        adjusted = False
        try:
            if int(options.get('interval_minutes','30')) < 30:
                options['interval_minutes']='30'
                adjusted=True
        except ValueError:
            pass
        remembered = options.get('remember_credentials', True)
        # Old distributed examples shipped these IDs without a user selection.
        sample_only = (raw.get('CONFIG_VERSION') != VERSION and not raw.get('DORM_NAME', '').strip()
                       and raw.get('BUILDING_ID') == '9552' and raw.get('ROOM_ID') == '9632')
        return {
            'options': options,
            'interval_adjusted': adjusted,
            'token': raw.get('GDMU_TOKEN', '') if remembered else '',
            'password': raw.get('SMTP_PASSWORD', '') if remembered else '',
            'target': {
                'campus': raw.get('CAMPUS_ID', ''),
                'campus_name': raw.get('CAMPUS_NAME', ''),
                'building_name': raw.get('BUILDING_NAME', ''),
                'room_name': raw.get('ROOM_NAME', ''),
                'building': '' if sample_only else raw.get('BUILDING_ID', ''),
                'room': '' if sample_only else raw.get('ROOM_ID', ''),
                'name': raw.get('DORM_NAME', ''),
            },
        }

    def save(self, options, token, password, target):
        values = {'CONFIG_VERSION': VERSION}
        for field, key in FIELDS.items():
            value = options.get(field, '')
            values[key] = ('true' if value else 'false') if field in BOOLS else str(value)
        remember = options.get('remember_credentials', True)
        values['GDMU_TOKEN'] = token if remember else ''
        values['SMTP_PASSWORD'] = password if remember else ''
        values['CAMPUS_ID'] = str(target.get('campus', ''))
        values['CAMPUS_NAME'] = str(target.get('campus_name', ''))
        values['BUILDING_NAME'] = str(target.get('building_name', ''))
        values['ROOM_NAME'] = str(target.get('room_name', ''))
        values['BUILDING_ID'] = str(target.get('building', ''))
        values['ROOM_ID'] = str(target.get('room', ''))
        values['DORM_NAME'] = str(target.get('name', ''))
        lines = [
            '# 广东医宿舍水电查询 v1.7.1 环境配置文件',
            '# 本文件由软件读写，不会执行其中的内容。',
            '# 记住凭证后会包含 Token 和 SMTP 授权码，请勿分享此文件。',
            '# 字符串使用双引号；AUTO_START=true 表示启动软件后校验并自动提醒。',
            '',
        ]
        lines.extend(f'{key}={json.dumps(value, ensure_ascii=False)}' for key, value in values.items())
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / '.env.tmp'
        temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        temporary.replace(self.path)
