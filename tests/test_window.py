from pathlib import Path
(Path(__file__).parent/'.tmp').mkdir(exist_ok=True)
from dataclasses import replace
from pathlib import Path
import sys
import unittest

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
from gdmu_wechat_window import Window, CloseAfterToken, WindowsDesktop, eligible, matches


SCHOOL=Window(100,20,12345,r'C:\WeChat\WeChatAppEx.exe','Chrome_WidgetWin_0','广东医缴费')


class Desktop:
    def __init__(self, windows):
        self.items={w.hwnd:w for w in windows}
        self.closed=[]
        self.honor=True
    def windows(self):return [w for w in self.items.values() if w.visible]
    def get(self,hwnd):return self.items.get(hwnd)
    def close(self,window):
        self.closed.append(window)
        if self.honor:self.items.pop(window.hwnd,None)
        return True


class Tests(unittest.TestCase):
    def setUp(self):
        self.now=10
        self.options={'wechat_close_after_token':True,'wechat_window_title':'','wechat_window_class':'','wechat_window_process':''}
        self.desktop=Desktop([SCHOOL])
        self.messages=[]
        self.closer=CloseAfterToken(lambda:self.options,self.messages.append,self.desktop,lambda:self.now)
    def test_wake_alone_never_closes_before_validation(self):
        self.closer.armed();self.now+=100;self.closer.poll()
        self.assertEqual(self.desktop.closed,[])
    def test_verified_token_closes_only_after_grace_and_confirms(self):
        self.closer.armed();self.closer.validated()
        self.now+=2.9;self.closer.poll();self.assertEqual(self.desktop.closed,[])
        self.now+=.2;self.closer.poll();self.assertEqual(self.desktop.closed,[SCHOOL])
        self.now+=2;self.closer.poll()
        self.assertIn('已关闭本轮',''.join(self.messages))
    def test_manually_opened_window_is_not_closed_without_software_wake(self):
        self.closer.validated();self.now+=10;self.closer.poll()
        self.assertEqual(self.desktop.closed,[])
    def test_reused_handle_or_pid_is_not_closed(self):
        for changed in (replace(SCHOOL,pid=21),replace(SCHOOL,created=12346),replace(SCHOOL,executable=r'C:\Other\WeChatAppEx.exe')):
            self.setUp();self.closer.armed();self.closer.validated()
            self.desktop.items[100]=changed
            self.now+=3;self.closer.poll();self.assertEqual(self.desktop.closed,[])
    def test_title_changes_to_other_miniapp_is_not_closed(self):
        self.closer.armed();self.closer.validated()
        self.desktop.items[100]=replace(SCHOOL,title='其他小程序')
        self.now+=3;self.closer.poll();self.assertEqual(self.desktop.closed,[])
    def test_duplicate_school_windows_are_not_guessed(self):
        self.desktop.items[101]=replace(SCHOOL,hwnd=101)
        self.closer.armed();self.closer.validated();self.now+=3;self.closer.poll()
        self.assertEqual(self.desktop.closed,[])
        self.assertIn('未唯一识别',''.join(self.messages))
    def test_main_windows_and_non_wechat_are_excluded(self):
        for w in (replace(SCHOOL,title='微信'),replace(SCHOOL,class_name='WeChatMainWndForPC'),replace(SCHOOL,executable=r'C:\Chrome\chrome.exe'),replace(SCHOOL,hwnd=0),replace(SCHOOL,hwnd=0xffff)):
            self.assertFalse(eligible(w))
            self.assertFalse(matches(w,self.options))
    def test_setting_disabled_or_selector_changed_cancels_pending_close(self):
        self.closer.armed();self.closer.validated();self.options['wechat_close_after_token']=False
        self.now+=3;self.closer.poll();self.assertEqual(self.desktop.closed,[])
        self.setUp();self.closer.armed();self.closer.validated();self.options['wechat_window_title']='changed'
        self.now+=3;self.closer.poll();self.assertEqual(self.desktop.closed,[])
    def test_window_appearing_after_wake_is_tracked(self):
        self.desktop.items.clear();self.closer.armed()
        self.desktop.items[100]=SCHOOL;self.now+=1;self.closer.poll()
        self.closer.validated();self.now+=3;self.closer.poll()
        self.assertEqual(self.desktop.closed,[SCHOOL])
    def test_window_reopened_during_delay_does_not_inherit_old_close(self):
        self.closer.armed();self.closer.validated()
        self.desktop.items.clear();self.desktop.items[101]=replace(SCHOOL,hwnd=101)
        self.now+=3;self.closer.poll()
        self.assertEqual(self.desktop.closed,[])
    def test_explicit_binding_matches_exact_class_process_and_title(self):
        target=replace(SCHOOL,title='充值缴费中心')
        self.desktop.items={100:target}
        self.options.update(wechat_window_title=target.title,wechat_window_class=target.class_name,wechat_window_process=target.process_name)
        self.closer.armed();self.closer.validated();self.now+=3;self.closer.poll()
        self.assertEqual(self.desktop.closed,[target])
    def test_application_ignoring_close_is_reported_not_claimed_closed(self):
        self.desktop.honor=False
        self.closer.armed();self.closer.validated();self.now+=3;self.closer.poll()
        self.now+=2;self.closer.poll()
        self.assertIn('窗口仍存在',''.join(self.messages))
    def test_next_wake_cycle_can_close_a_new_window(self):
        self.closer.armed();self.closer.validated();self.now+=3;self.closer.poll();self.now+=2;self.closer.poll()
        nextwindow=replace(SCHOOL,hwnd=102,created=23456)
        self.desktop.items[102]=nextwindow
        self.closer.armed();self.closer.validated();self.now+=3;self.closer.poll()
        self.assertEqual(self.desktop.closed,[SCHOOL,nextwindow])


class Win32Tests(unittest.TestCase):
    def test_native_inspection_and_wm_close_only_on_owned_test_window(self):
        import tkinter as tk
        import ctypes
        from ctypes import wintypes as wt
        root=tk.Tk();root.withdraw()
        window=tk.Toplevel(root);window.title('广东医缴费 · 本机关闭测试')
        closed=[]
        window.protocol('WM_DELETE_WINDOW',lambda:(closed.append(True),window.destroy()))
        try:
            root.update()
            native=WindowsDesktop()
            native.user.GetAncestor.argtypes=[wt.HWND,wt.UINT]
            native.user.GetAncestor.restype=wt.HWND
            hwnd=int(native.user.GetAncestor(window.winfo_id(),2))
            actual=native.get(hwnd)
            self.assertIsNotNone(actual)
            self.assertGreater(actual.created,0)
            self.assertFalse(eligible(actual))  # Python/test GUI must never match.
            synthetic=replace(actual,executable=r'C:\ControlledTest\WeChatAppEx.exe')
            # Only this test-owned handle is substituted. No other window is read
            # or receives a close message in this test.
            native.get=lambda handle:synthetic if handle==hwnd else None
            self.assertTrue(native.close(synthetic))
            root.update()
            self.assertEqual(closed,[True])
        finally:
            root.destroy()


if __name__=='__main__':unittest.main(verbosity=2)
