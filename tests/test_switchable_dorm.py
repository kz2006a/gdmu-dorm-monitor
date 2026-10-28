import sys
sys.dont_write_bytecode = True
import importlib.machinery
import importlib.util
import json
import sys
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

OUT = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(OUT))
import gdmu_balance as api


class Response:
    def __init__(self, info, code='00'):
        self.data = json.dumps({'ret_code': code, 'info': api.encrypt_json(info)}).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.data


class ApiTests(unittest.TestCase):
    def test_real_api_shapes(self):
        calls = []
        fixtures = [
            [{'xiaoQuId': 1, 'xiaoQu': '校区甲'}],
            [{'louDongId': 101, 'louDong': '甲楼', 'xiaoQuId': 1}],
            [{'roomId': 1001, 'room': '101'}],
            {'electricityBalance': '133', 'waterBalance': '0'},
        ]
        def opened(req, timeout):
            calls.append(req)
            return Response(fixtures[len(calls)-1])
        with patch.object(api.urllib.request, 'urlopen', side_effect=opened):
            self.assertEqual(api.list_campuses('local-test')[0]['id'], 1)
            self.assertEqual(api.list_buildings('local-test', 1)[0]['id'], 101)
            self.assertEqual(api.list_rooms('local-test', 1, 101)[0]['id'], 1001)
            self.assertEqual(api.query_balance('local-test', 101, 1001)['waterBalance'], '0')
        self.assertEqual(calls[0].method, 'GET')
        self.assertIsNone(calls[0].data)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)
        self.assertEqual(api.decrypt_json(params['param'][0]), {})
        expected = [{'xiao_qu_id': 1}, {'xiao_qu_id': 1, 'lou_dong_id': 101}, {'buildingId': 101, 'roomId': 1001}]
        for req, plain in zip(calls[1:], expected):
            self.assertEqual(req.method, 'POST')
            self.assertEqual(api.decrypt_json(json.loads(req.data)['param']), plain)
        self.assertEqual(calls[3].full_url, api.URL)

    def test_expired_session_and_endpoint_limit(self):
        with patch.object(api.urllib.request, 'urlopen', return_value=Response({}, '06')):
            with self.assertRaisesRegex(ValueError, '登录凭证已失效'):
                api.query_balance('local-test', 101, 1001)
        with self.assertRaisesRegex(ValueError, '只支持'):
            api.api_request('local-test', 'api/payment/pay', {})


class FakeBackend:
    def __init__(self):
        self.calls = []
    def list_campuses(self, token):
        return [{'id': 1, 'name': '校区甲'}, {'id': 2, 'name': '校区乙'}]
    def list_buildings(self, token, campus):
        self.calls.append(('buildings', campus))
        return [{'id': 101, 'name': '甲楼'}, {'id': 102, 'name': '乙楼'}]
    def list_rooms(self, token, campus, building):
        self.calls.append(('rooms', campus, building))
        return [{'id': 1001, 'name': '101'}, {'id': 1002, 'name': '102'}]
    def query_balance(self, token, building, room):
        self.calls.append(('balance', building, room))
        return {'electricityBalance': '133' if room == 1001 else '88', 'waterBalance': '0'}


class GuiTests(unittest.TestCase):
    def test_switching_does_not_show_previous_dorm_balance(self):
        loader = importlib.machinery.SourceFileLoader('gdmu_desktop', str(OUT / 'gdmu_desktop.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        gui = importlib.util.module_from_spec(spec)
        loader.exec_module(gui)
        root = gui.tk.Tk()
        root.withdraw()
        backend = FakeBackend()
        app = gui.BalanceApp(root, backend)
        def wait():
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertFalse(app.busy)
            root.update_idletasks()
        try:
            app.token.set('local-test')
            app.load_campuses(); wait()
            app.campus_box.current(0); app.choose_campus(); wait()
            app.building_box.current(0); app.choose_building(); wait()
            app.room_box.current(0); app.choose_room()
            app.query_selected(); wait()
            self.assertEqual(app.electricity.get(), '133')
            self.assertEqual(app.water.get(), '0')
            app.room_box.current(1); app.choose_room()
            self.assertEqual(app.electricity.get(), '—')
            app.query_selected(); wait()
            self.assertEqual(app.electricity.get(), '88')
            self.assertEqual(backend.calls[-1], ('balance', 101, 1002))
            app.building_box.current(1); app.choose_building(); wait()
            self.assertEqual(app.electricity.get(), '—')
            self.assertEqual(app.room_box.current(), -1)
            self.assertEqual(backend.calls[-1], ('rooms', 1, 102))
            app.campus_box.current(1); app.choose_campus(); wait()
            self.assertEqual(app.room_box.get(), '')
            self.assertEqual(backend.calls[-1], ('buildings', 2))
            app.token.set('changed'); app.token_changed()
            self.assertEqual(app.campuses, [])
            self.assertEqual(app.campus_box.get(), '')
            root.attributes('-alpha', 0.0)
            root.deiconify()
            root.geometry('760x600')
            root.update()
            region = root.tk.splitlist(app.canvas.cget('scrollregion'))
            self.assertGreater(float(region[3]), app.canvas.winfo_height())
            footer = [child for child in root.winfo_children() if child.cget('bg') == '#e8eef7'][0]
            self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), root.winfo_height())
            root.withdraw()
            print('Small-window layout verified: body scrolls; status remains visible.')
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
