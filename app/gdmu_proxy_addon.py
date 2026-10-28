"""mitmdump addon: copy only the school's successful login response.

Never logs request headers, codes, bodies or whole flows. All other hosts are
tunneled by --allow-hosts. Domain-wide TLS is necessary to see the HTTPS path.
"""
import asyncio
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid

from mitmproxy import ctx

BASE = Path(os.environ['GDMU_PROXY_BASE']).resolve()
NONCE = os.environ['GDMU_PROXY_NONCE']
PARENT = int(os.environ['GDMU_PROXY_PARENT'])

# Load by path so the standalone engine does not depend on a user's PYTHONPATH.
spec = importlib.util.spec_from_file_location('gdmu_proxy_helper', BASE / 'app' / 'gdmu_proxy.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class SchoolLoginCapture:
    def __init__(self):
        self.task = None
        self.parent_handle = None

    def running(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        self.parent_handle = kernel.OpenProcess(0x00100000, False, PARENT)
        if not self.parent_handle:
            ctx.master.shutdown()
            return
        helper.atomic_json(BASE / 'data' / 'https-proxy' / 'ready.json', {'nonce': NONCE})
        self.task = asyncio.create_task(self.watch_parent())

    async def watch_parent(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        try:
            while kernel.WaitForSingleObject(self.parent_handle, 0) == 258:
                try:
                    stop = BASE / 'data' / 'https-proxy' / 'stop.json'
                    if stop.exists() and json.loads(stop.read_text(encoding='utf-8')).get('nonce') == NONCE:
                        break
                except (OSError, ValueError):
                    pass
                await asyncio.sleep(.5)
            try:
                helper.restore_route(BASE / 'data' / 'proxy-restore.json', nonce=NONCE)
            finally:
                ctx.master.shutdown()
        finally:
            kernel.CloseHandle(self.parent_handle)
            self.parent_handle = None

    def response(self, flow):
        request, response = flow.request, flow.response
        if (request.scheme != 'https' or request.host.lower() != 'pay.gdmu.edu.cn' or
                request.port != 443 or request.method != 'POST' or
                request.path.split('?', 1)[0] != '/pmccl/api/code2Session' or
                response.status_code != 200):
            return
        inbox = BASE / 'token-sync'
        marker = inbox / 'enabled.flag'
        try:
            age = time.time() - marker.stat().st_mtime
            if age < 0 or age >= 30:
                return
            if len(response.raw_content or b'') > 1024 * 1024:
                return
            body = response.get_text(strict=True)
            if not body or len(body.encode('utf-8')) > 1024 * 1024:
                return
            parsed = json.loads(body)
            if not isinstance(parsed, dict) or str(parsed.get('ret_code')) != '00':
                return
            name = str(621355968000000000 + time.time_ns() // 100) + '-' + uuid.uuid4().hex + '.login.json'
            temporary = inbox / (name + '.tmp')
            temporary.write_text(body, encoding='utf-8')
            temporary.replace(inbox / name)
        except (OSError, ValueError, UnicodeError):
            # A malformed response does not disturb the user's original request.
            return

    def done(self):
        if self.task:
            self.task.cancel()


addons = [SchoolLoginCapture()]
