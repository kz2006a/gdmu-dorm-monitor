"""Query your authorized GDMU dorm balance; credentials stay in memory."""
import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
except ImportError:
    print('缺少依赖，请执行：python -m pip install cryptography', file=sys.stderr)
    raise SystemExit(1)

URL = 'https://pay.gdmu.edu.cn/pmccl/api/payment/balance'
BASE_URL = 'https://pay.gdmu.edu.cn/pmccl/'
KEY = b'lrmp1106' + b'0' * 16
IV = bytes(8)
SAMPLE_PARAM = 'fH5G9wrHrHC7m6Hl1GuuK/1zqOI1ZcXhhy8EJY6GfNs='
SAMPLE_INFO = 'COfv+vJabewj1CSQaj6TcYu+VYtlH13Ugw+h+l4Myk0oS9/tw8lkN0viBYQFRZrzyYsQmrcqcq4='


def encrypt_json(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    pad = 8 - len(raw) % 8
    raw += bytes([pad]) * pad
    worker = Cipher(TripleDES(KEY), modes.CBC(IV)).encryptor()
    return base64.b64encode(worker.update(raw) + worker.finalize()).decode('ascii')


def decrypt_json(value):
    raw = base64.b64decode(value, validate=True)
    if not raw or len(raw) % 8:
        raise ValueError('返回密文长度异常，接口格式可能已改变。')
    worker = Cipher(TripleDES(KEY), modes.CBC(IV)).decryptor()
    raw = worker.update(raw) + worker.finalize()
    pad = raw[-1]
    if not 1 <= pad <= 8 or raw[-pad:] != bytes([pad]) * pad:
        raise ValueError('解密校验失败，小程序的数据处理方式可能已改变。')
    return json.loads(raw[:-pad].decode('utf-8'))


def api_request(token, path, parameters, method='POST'):
    allowed = {
        'api/payment/balance', 'api/room/campusList',
        'api/room/buildingList', 'api/room/roomList',
    }
    if path not in allowed or method not in ('GET', 'POST'):
        raise ValueError('此工具只支持宿舍列表与余量查询。')
    token = token.strip()
    if not token:
        raise ValueError('请先填写 Token。')
    payload = {'param': encrypt_json(parameters)}
    url = BASE_URL + path
    body = None
    if method == 'GET':
        url += '?' + urllib.parse.urlencode(payload)
    else:
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'token': token,
            'Referer': 'https://servicewechat.com/wxab6b0c9d831e0bfd/22/page-frame.html',
            'User-Agent': 'Mozilla/5.0',
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read(1024 * 1024).decode('utf-8'))
    code = str(result.get('ret_code', ''))
    if code == '06':
        raise ValueError('登录凭证已失效，请在微信重新查询，并更新本机 Token。')
    if code != '00':
        # Do not dump the raw response: it could contain session information.
        raise ValueError(f'接口未返回成功，ret_code={code!r}。请在小程序中核对登录状态。')
    info = result.get('info')
    if not isinstance(info, str):
        raise ValueError('返回 info 不是预期的密文字符串，需重新检查接口格式。')
    return decrypt_json(info)


def normalize_items(data, id_key, name_key):
    if not isinstance(data, list):
        raise ValueError('宿舍列表格式与预期不符。')
    items = []
    for row in data:
        if not isinstance(row, dict) or row.get(id_key) is None or row.get(name_key) is None:
            raise ValueError('宿舍列表缺少编号或名称。')
        items.append({'id': row[id_key], 'name': str(row[name_key]), 'raw': row})
    return items


def list_campuses(token):
    data = api_request(token, 'api/room/campusList', {}, 'GET')
    return normalize_items(data, 'xiaoQuId', 'xiaoQu')


def list_buildings(token, campus_id):
    data = api_request(token, 'api/room/buildingList', {'xiao_qu_id': campus_id})
    items = normalize_items(data, 'louDongId', 'louDong')
    return [item for item in items if item['raw'].get('xiaoQuId') is None
            or str(item['raw']['xiaoQuId']) == str(campus_id)]


def list_rooms(token, campus_id, building_id):
    data = api_request(token, 'api/room/roomList', {
        'xiao_qu_id': campus_id, 'lou_dong_id': building_id,
    })
    return normalize_items(data, 'roomId', 'room')


def query_balance(token, building_id, room_id):
    info = api_request(token, 'api/payment/balance', {
        'buildingId': building_id, 'roomId': room_id,
    })
    if not isinstance(info, dict) or not any(
        k in info for k in ('electricityBalance', 'waterBalance')
    ):
        raise ValueError('已解密，但未发现预期的水电余量字段。')
    return info


def main():
    parser = argparse.ArgumentParser(description='广东医缴费：个人宿舍只读余量查询原型')
    parser.add_argument('--building-id', type=int, default=1)
    parser.add_argument('--room-id', type=int, default=1)
    parser.add_argument('--decode', metavar='BASE64', help='仅离线解码，不访问网络')
    parser.add_argument('--self-test', action='store_true', help='用虚构编号的协议样例离线验证')
    args = parser.parse_args()
    if args.self_test:
        request = {'buildingId': 1, 'roomId': 1}
        expected = {'electricityBalance': '100', 'waterBalance': '10'}
        if decrypt_json(SAMPLE_PARAM) != request or encrypt_json(request) != SAMPLE_PARAM:
            raise ValueError('请求样本验证失败。')
        if decrypt_json(SAMPLE_INFO) != expected:
            raise ValueError('响应样本验证失败。')
        print('离线协议样例验证通过：虚构目标 1/1，示例 100 度电、10 吨水。')
        return
    if args.decode is not None:
        print(json.dumps(decrypt_json(args.decode), ensure_ascii=False, indent=2))
        return
    token = os.environ.get('GDMU_TOKEN', '').strip()
    if not token:
        token = getpass.getpass('粘贴 Fiddler 中自己的 token 值（输入不回显）：').strip()
    if not token:
        raise ValueError('Token 不能为空。')
    info = query_balance(token, args.building_id, args.room_id)
    print(json.dumps({
        'queriedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'buildingId': args.building_id,
        'roomId': args.room_id,
        'electricityBalance': info.get('electricityBalance'),
        'electricityUnit': '度',
        'waterBalance': info.get('waterBalance'),
        'waterUnit': '吨',
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(f'查询失败：HTTP {exc.code}。请检查登录凭证和网络。', file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError:
        print('查询失败：无法连接缴费站点。请检查网络、代理与证书配置。', file=sys.stderr)
        sys.exit(2)
    except (ValueError, OSError) as exc:
        print(f'查询失败：{exc}', file=sys.stderr)
        sys.exit(2)
    except (EOFError, KeyboardInterrupt):
        print('\n已取消。', file=sys.stderr)
        sys.exit(130)
