"""Receive only local code2Session response files, never request headers."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time

import gdmu_balance as api

PACKET_NAME = re.compile(r'^\d{16,20}-[0-9a-fA-F]{32}\.login\.json$')


def fingerprint(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()[:12]


def claims(token):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        value = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def guard_candidate(current, candidate):
    old, new = claims(current), claims(candidate)
    for field in ('sub', 'openid', 'userId', 'userid', 'user_id', 'studentNo', 'student_no'):
        if old.get(field) is not None and new.get(field) is not None and old[field] != new[field]:
            raise ValueError('候选 Token 的账号标识与当前凭证不同，未自动替换。')
    old_iat, new_iat = old.get('iat'), new.get('iat')
    if isinstance(old_iat, (int, float)) and isinstance(new_iat, (int, float)) and new_iat < old_iat:
        raise ValueError('候选 Token 的签发时间早于当前凭证，已忽略过旧响应。')


def extract_response(text):
    if len(text) > 1024 * 1024:
        raise ValueError('登录响应过大，已忽略。')
    try:
        response = json.loads(text)
    except ValueError:
        raise ValueError('登录响应不是完整 JSON，未更新 Token。') from None
    if not isinstance(response, dict) or str(response.get('ret_code', '')) != '00':
        raise ValueError('登录响应未返回成功状态，未更新 Token。')
    info = response.get('info')
    if isinstance(info, str):
        try:
            info = api.decrypt_json(info)
        except Exception:
            raise ValueError('登录 info 解码失败，未更新 Token。') from None
    if not isinstance(info, dict) or not isinstance(info.get('token'), str):
        raise ValueError('登录响应没有 Token，可能仍需在小程序完成学校登录。')
    token = info['token'].strip()
    if not token or len(token) > 16384 or '\r' in token or '\n' in token:
        raise ValueError('登录响应的 Token 格式异常，未更新。')
    return token


def fiddler_script(directory):
    inbox = str((Path(directory) / 'token-sync').resolve())
    quoted = json.dumps(inbox, ensure_ascii=True)
    return '''// GDMU v1.3.0: paste INSIDE the existing OnBeforeResponse function.
// Only the successful code2Session RESPONSE is copied. No request token is used.
if (oSession.HostnameIs("pay.gdmu.edu.cn") &&
    oSession.HTTPMethodIs("POST") && oSession.responseCode == 200) {
    var gdmuSyncPath: String = oSession.PathAndQuery;
    var gdmuSyncQ: int = gdmuSyncPath.IndexOf("?");
    if (gdmuSyncQ >= 0) gdmuSyncPath = gdmuSyncPath.Substring(0, gdmuSyncQ);
    if (gdmuSyncPath == "/pmccl/api/code2Session") {
        try {
            var gdmuSyncDir: String = __DIRECTORY__;
            var gdmuSyncLease: String = System.IO.Path.Combine(gdmuSyncDir, "enabled.flag");
            if (System.IO.File.Exists(gdmuSyncLease)) {
                var gdmuSyncAge: double = System.DateTime.UtcNow.Subtract(System.IO.File.GetLastWriteTimeUtc(gdmuSyncLease)).TotalSeconds;
                if (gdmuSyncAge >= 0 && gdmuSyncAge < 30) {
                    oSession.utilDecodeResponse();
                    var gdmuSyncBody: String = oSession.GetResponseBodyAsString();
                    if (gdmuSyncBody.Length > 0 && gdmuSyncBody.Length < 1048576) {
                        var gdmuSyncName: String = System.DateTime.UtcNow.Ticks.ToString() + "-" + System.Guid.NewGuid().ToString("N") + ".login.json";
                        var gdmuSyncFile: String = System.IO.Path.Combine(gdmuSyncDir, gdmuSyncName);
                        var gdmuSyncTemp: String = gdmuSyncFile + ".tmp";
                        System.IO.File.WriteAllText(gdmuSyncTemp, gdmuSyncBody, new System.Text.UTF8Encoding(false));
                        System.IO.File.Move(gdmuSyncTemp, gdmuSyncFile);
                        Fiddler.FiddlerApplication.Log.LogString("GDMU: login response queued for local verification.");
                    }
                }
            }
        } catch (gdmuSyncError) {
            Fiddler.FiddlerApplication.Log.LogString("GDMU: could not write local sync packet. Regenerate the snippet if the software folder moved.");
        }
    }
}
'''.replace('__DIRECTORY__', quoted)


class TokenInbox:
    def __init__(self, directory, notify, clock=time.time):
        self.directory = (Path(directory) / 'token-sync').resolve()
        self.notify, self.clock = notify, clock
        self.marker = self.directory / 'enabled.flag'
        self.owner = os.urandom(16).hex()
        self.last_pulse = 0
        self.pending = []
        self.seen = {}

    def pulse(self):
        now = self.clock()
        if now - self.last_pulse >= 5 or not self.marker.exists():
            self.directory.mkdir(parents=True, exist_ok=True)
            self.marker.write_text(self.owner, encoding='ascii')
            self.last_pulse = now

    def files(self):
        if not self.directory.is_dir():
            return []
        result = []
        for path in self.directory.glob('*.login.json'):
            if PACKET_NAME.fullmatch(path.name) and path.is_file() and not path.is_symlink() and path.resolve().parent == self.directory:
                result.append(path)
        return sorted(result, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)

    def collect(self):
        now = self.clock()
        for path in reversed(self.files()[:32]):
            try:
                stat = path.stat()
                if stat.st_size > 1024 * 1024 or now - stat.st_mtime > 300 or stat.st_mtime - now > 30:
                    self.notify('已忽略过期或异常的本地登录响应。')
                    continue
                token = extract_response(path.read_text(encoding='utf-8-sig'))
                mark = fingerprint(token)
                if mark in self.seen and now - self.seen[mark] < 10:
                    continue
                self.seen[mark] = now
                self.pending.append((token, now))
                self.pending = self.pending[-8:]
                self.notify('已收到登录响应，等待验证候选 Token（指纹 ' + mark + '）。')
            except ValueError as exc:
                self.notify(str(exc))
            except OSError:
                self.notify('本地登录响应读取失败，请检查目录权限。')
            finally:
                # Delete only owned protocol files inside the checked inbox.
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        self.seen = {key: timestamp for key, timestamp in self.seen.items() if now - timestamp < 600}

    def take(self):
        now = self.clock()
        while self.pending:
            token, received = self.pending.pop()  # prefer the latest fresh response
            if now - received <= 300:
                self.pending.clear()
                return token
        return None

    def close(self):
        try:
            if self.marker.read_text(encoding='ascii') == self.owner:
                self.marker.unlink(missing_ok=True)
        except OSError:
            pass
        self.pending.clear()
        try:
            paths = self.files()
        except OSError:
            paths = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        self.last_pulse = 0
