"""Private loopback HTTPS capture, certificate setup and reversible WinINET routing.

No OS changes are made on import. Trust/routing are changed only by explicit UI
actions. The engine is shipped locally; no download or shell command is run here.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

NAMES = ('ProxyEnable', 'ProxyServer', 'ProxyOverride')
KEY = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
HOST = 'pay.gdmu.edu.cn'
ALLOW_HOST = r'^pay\.gdmu\.edu\.cn:443$'
PORT = 18765
HIDDEN = 0x08000000 if sys.platform == 'win32' else 0


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


class WindowsSettings:
    def read(self, names=NAMES):
        import winreg
        result = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            for name in names:
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                    result[name] = [value, kind]
                except FileNotFoundError:
                    result[name] = None
        return result

    def write(self, values):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name, item in values.items():
                if item is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
                else:
                    winreg.SetValueEx(key, name, 0, item[1], item[0])
        wininet = ctypes.WinDLL('wininet', use_last_error=True)
        for flag in (39, 37):
            if not wininet.InternetSetOptionW(None, flag, None, 0):
                raise OSError('Windows 未能广播代理更新，请检查网络设置。')


def load_lease(path):
    path = Path(path)
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or value.get('schema') != 1 or
            set(value.get('original', {})) != set(NAMES) or
            set(value.get('expected', {})) != set(NAMES)):
        raise ValueError('代理恢复记录无效，请在 Windows 设置中检查代理。')
    return value


def restore_route(path, settings=None, nonce=None):
    """Compare before restoring; never overwrite another tool's later changes."""
    settings = settings or WindowsSettings()
    lease = load_lease(path)
    if lease is None:
        return 'none'
    if nonce is not None and lease['nonce'] != nonce:
        return 'different-owner'
    current = settings.read()
    if current == lease['original']:
        Path(path).unlink(missing_ok=True)
        return 'already-restored'
    if current != lease['expected']:
        # Keep the journal for diagnosis. Another program/user owns the settings.
        return 'changed-externally'
    settings.write(lease['original'])
    if settings.read() != lease['original']:
        raise OSError('原代理未完全恢复，请使用“恢复网络”重试。')
    Path(path).unlink(missing_ok=True)
    return 'restored'


def activate_route(path, port, parent_pid, nonce, settings=None):
    settings = settings or WindowsSettings()
    old = settings.read()
    pac = settings.read(('AutoConfigURL',)).get('AutoConfigURL')
    if (old.get('ProxyEnable') and old['ProxyEnable'][0]) or (pac and pac[0]):
        raise ValueError('检测到已有系统代理或 PAC。请先关闭 Fiddler、系统代理或相关代理软件，再开启内置同步。')
    expected = {'ProxyEnable': [1, 4], 'ProxyServer': [f'127.0.0.1:{port}', 1],
                'ProxyOverride': ['<local>', 1]}
    lease = {'schema': 1, 'nonce': nonce, 'parent_pid': parent_pid,
             'original': old, 'expected': expected, 'created': time.time()}
    atomic_json(path, lease)  # Recovery record must exist before the first mutation.
    try:
        settings.write(expected)
        if settings.read() != expected:
            raise OSError('Windows 未接入本地代理。')
    except Exception:
        # A partial write belongs to this activation; restore it immediately.
        settings.write(old)
        if settings.read() == old:
            Path(path).unlink(missing_ok=True)
        raise
    return lease


def cert_path(directory):
    return Path(directory) / 'data' / 'https-proxy' / 'mitmproxy-ca-cert.cer'


def certificate_thumbprint(directory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    raw = cert_path(directory).read_bytes()
    cert = x509.load_pem_x509_certificate(raw) if b'BEGIN CERTIFICATE' in raw else x509.load_der_x509_certificate(raw)
    return cert.fingerprint(hashes.SHA1()).hex().upper()


def certificate_trusted(directory):
    try:
        thumb = certificate_thumbprint(directory)
        import ssl
        return any(hashlib.sha1(raw).hexdigest().upper() == thumb
                   for raw, encoding, trust in ssl.enum_certificates('ROOT'))
    except (OSError, ValueError, AttributeError):
        return False


def certificate_action(directory, install):
    if sys.platform != 'win32':
        raise ValueError('证书设置仅支持 Windows。')
    base = Path(directory)
    if not cert_path(base).is_file():
        raise ValueError('请先点击“准备内置引擎”，生成本目录专用证书。')
    receipt = base / 'data' / 'certificate-install.json'
    thumb = certificate_thumbprint(base)
    if install and certificate_trusted(base):
        return '当前证书已受信任。'
    if not install:
        if not receipt.exists() or json.loads(receipt.read_text(encoding='utf-8')).get('thumbprint') != thumb:
            raise ValueError('没有本软件安装此证书的记录，未自动删除证书。')
    system = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'certutil.exe'
    args = [str(system), '-user', '-addstore', 'Root', str(cert_path(base))] if install else [str(system), '-user', '-delstore', 'Root', thumb]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=HIDDEN, timeout=45)
    if result.returncode:
        raise ValueError('Windows 证书操作未成功或已取消，请检查证书提示。')
    if install:
        atomic_json(receipt, {'thumbprint': thumb})
        if not certificate_trusted(base):
            raise ValueError('证书命令完成，但尚未确认信任状态，请重新检查。')
        return '已安装到当前 Windows 用户的受信任根证书。'
    receipt.unlink(missing_ok=True)
    return '已移除本目录对应的用户根证书。'


class ProxyService:
    def __init__(self, directory, settings=None):
        self.base = Path(directory).resolve()
        self.settings = settings or WindowsSettings()
        self.data = self.base / 'data' / 'https-proxy'
        self.lease = self.base / 'data' / 'proxy-restore.json'
        self.process = None
        self.nonce = uuid.uuid4().hex
        self.connected = False

    def command(self):
        engine = self.base / 'runtime' / 'https' / 'mitmdump.exe'
        addon = self.base / 'app' / 'gdmu_proxy_addon.py'
        if not engine.is_file() or not addon.is_file():
            raise ValueError('内置引擎文件不完整，请完整解压新版程序包。')
        return [str(engine), '--listen-host', '127.0.0.1', '--listen-port', str(PORT),
                '--allow-hosts', ALLOW_HOST, '--set', f'confdir={self.data}',
                '--set', 'ssl_insecure=false', '--set', 'termlog_verbosity=error',
                '--set', 'flow_detail=0', '--set', 'onboarding=false', '-s', str(addon)]

    @property
    def alive(self):
        return self.process is not None and self.process.poll() is None

    def recover(self):
        return restore_route(self.lease, self.settings)

    def prepare(self, timeout=55):
        if self.alive:
            return
        if self.lease.exists():
            result = self.recover()
            if result == 'changed-externally':
                raise ValueError('代理设置已被外部修改。请先检查网络并点击“恢复网络”，确认后重试。')
        self.data.mkdir(parents=True, exist_ok=True)
        ready = self.data / 'ready.json'
        ready.unlink(missing_ok=True)
        (self.data / 'stop.json').unlink(missing_ok=True)
        env = os.environ.copy()
        # Parent may be PyInstaller: independent frozen child must unpack itself.
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        env['GDMU_PROXY_BASE'] = str(self.base)
        env['GDMU_PROXY_PARENT'] = str(os.getpid())
        env['GDMU_PROXY_NONCE'] = self.nonce
        # Child imports only our addon/helper, not the GUI or saved .env.
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', PORT))
            except OSError:
                raise ValueError(f'本地端口 {PORT} 被占用；请关闭占用它的程序后重试。') from None
        self.process = subprocess.Popen(self.command(), cwd=self.base, env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, creationflags=HIDDEN)
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if not self.alive:
                code = self.process.returncode
                raise ValueError(f'内置 HTTPS 引擎启动失败（退出码 {code}），未修改系统代理。')
            if ready.exists():
                try:
                    value = json.loads(ready.read_text(encoding='utf-8'))
                    if value.get('nonce') == self.nonce and cert_path(self.base).exists():
                        return
                except (ValueError, OSError):
                    pass
            time.sleep(.15)
        self.shutdown()
        raise ValueError('内置引擎启动超时，系统代理未启用。')

    def connect(self):
        if not self.alive:
            raise ValueError('内置引擎未运行，请先准备引擎。')
        if not certificate_trusted(self.base):
            raise ValueError('请先安装并信任本目录的 HTTPS 证书。')
        if not self.connected:
            activate_route(self.lease, PORT, os.getpid(), self.nonce, self.settings)
            self.connected = True

    def disconnect(self):
        result = restore_route(self.lease, self.settings, self.nonce)
        self.connected = False
        return result

    def shutdown(self):
        # Route first, engine second: avoid pointing Windows at a dead listener.
        try:
            result = self.disconnect()
        finally:
            # Ask the actual engine to exit. A standalone one-file executable has
            # a bootloader parent, so killing just Popen.pid can orphan its worker.
            if self.data.exists():
                atomic_json(self.data / 'stop.json', {'nonce': self.nonce})
            if self.alive:
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if sys.platform == 'win32':
                        tool = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
                        subprocess.run([str(tool), '/PID', str(self.process.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=HIDDEN, timeout=8)
                    else:
                        self.process.kill()
                    self.process.wait(timeout=5)
        return result
