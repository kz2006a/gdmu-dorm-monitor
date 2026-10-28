"""Campus blue/white desktop adaptation of the installed gdmu-ui-design skill.

View composition only. Login, queries, SMTP, proxy and close-window policies
remain in the existing controllers. No assets are taken from reference previews.
"""
import tkinter as tk
import time
from tkinter import ttk

BLUE = '#0075C2'
BLUE_LIGHT = '#EAF5FC'
BG = '#F3F3F2'
WHITE = '#FFFFFF'
INK = '#1D2B36'
MUTED = '#627584'
LINE = '#E6EBEE'
GREEN = '#16805E'
FONT = 'Microsoft YaHei UI'


def text(parent, value='', size=10, color=INK, bold=False, **kw):
    label=tk.Label(parent,text=value,bg=parent.cget('bg'),fg=color,
                   font=(FONT,size,'bold' if bold else 'normal'),**kw)
    if 'wraplength' in kw:
        preferred=kw['wraplength']
        state={'job':None,'width':None,'wrap':preferred}
        def apply():
            state['job']=None
            if not label.winfo_exists(): return
            width=max(80,min(preferred,parent.winfo_width()-24))
            if abs(width-state['wrap'])>=3:
                state['wrap']=width; label.configure(wraplength=width)
        def schedule(event):
            if getattr(parent._root(),'_ui_closing',False): return
            if state['width']==event.width: return
            state['width']=event.width
            if state['job']: label.after_cancel(state['job'])
            state['job']=label.after(70,apply)
        parent.bind('<Configure>',schedule,add='+')
    return label


def theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=(FONT, 10), background=WHITE, foreground=INK)
    style.configure('TFrame', background=WHITE)
    style.configure('TLabel', background=WHITE, foreground=INK)
    style.configure('TEntry', padding=(10, 8), fieldbackground=WHITE, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
    style.map('TEntry', bordercolor=[('focus', BLUE)], fieldbackground=[('disabled', '#F4F6F7')])
    style.configure('TCombobox', padding=(8, 7), fieldbackground=WHITE, bordercolor=LINE, arrowcolor=BLUE)
    style.map('TCombobox', fieldbackground=[('readonly', WHITE), ('disabled', '#F4F6F7')], foreground=[('disabled', MUTED)])
    style.configure('TButton', padding=(14, 9), background=WHITE, foreground=BLUE, borderwidth=1,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, focuscolor=BLUE)
    style.map('TButton', background=[('active', BLUE_LIGHT), ('disabled', '#F2F5F7')], foreground=[('disabled', '#8997A0')])
    style.configure('Primary.TButton', background=BLUE, foreground=WHITE, borderwidth=0, focuscolor='#B9E4FC')
    style.map('Primary.TButton', background=[('disabled', '#BCD8EA'), ('active', '#0068AD')], foreground=[('disabled', WHITE)])
    style.configure('Quiet.TButton', borderwidth=0, background=WHITE, foreground=MUTED, padding=(10, 7))
    style.configure('Nav.TButton', anchor='w', padding=(20, 15), background=WHITE, foreground=MUTED, borderwidth=0)
    style.map('Nav.TButton', background=[('active', '#F2F8FC')])
    style.configure('Selected.Nav.TButton', background=BLUE_LIGHT, foreground=BLUE, font=(FONT, 10, 'bold'))
    style.map('Selected.Nav.TButton', background=[('active', BLUE_LIGHT)])
    style.configure('Tab.TButton', background=WHITE, foreground=MUTED, borderwidth=0, padding=(20, 12))
    style.map('Tab.TButton', background=[('active', '#F5FAFD')])
    style.configure('Selected.Tab.TButton', background=WHITE, foreground=BLUE, font=(FONT, 10, 'bold'))
    style.map('Selected.Tab.TButton', background=[('active', WHITE)])
    style.configure('TCheckbutton', background=WHITE, padding=(0, 4), foreground=INK)
    style.map('TCheckbutton', background=[('active', WHITE)])
    style.configure('TNotebook', background=WHITE, borderwidth=0, tabmargins=(0, 5, 0, 12))
    style.configure('TNotebook.Tab', padding=(22, 12), background=WHITE, foreground=MUTED, borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', BLUE_LIGHT)], foreground=[('selected', BLUE)])
    style.configure('TLabelframe', background=WHITE, bordercolor=LINE, borderwidth=1, relief='solid')
    style.configure('TLabelframe.Label', foreground=BLUE, background=WHITE, font=(FONT, 10, 'bold'))
    style.configure('Vertical.TScrollbar', background='#D8E3E9', troughcolor=BG, borderwidth=0, arrowsize=11)
    style.configure('Treeview', background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=34, bordercolor=LINE)
    style.configure('Treeview.Heading', background=BLUE_LIGHT, foreground=BLUE, padding=8)
    root.configure(bg=BG)


def icon(parent, kind, size=44, bg=BLUE_LIGHT, color=BLUE, tile=False):
    canvas = tk.Canvas(parent, width=size, height=size, bg=parent.cget('bg'), highlightthickness=0)
    s = size / 48
    def line(points, **kw):
        return canvas.create_line(*[v*s for v in points], fill=color, width=max(1.5, 2*s), capstyle='round', joinstyle='round', **kw)
    def rect(points):
        canvas.create_rectangle(*[v*s for v in points], outline=color, width=2*s)
    if tile:
        radius=size*.26
        for y in range(1,size-1):
            distance=max(radius-y,y-(size-radius),0)
            inset=radius-(max(0,radius*radius-distance*distance)**.5) if distance else 1
            fraction=y/(size-1)
            start,end=(168,224,242),(221,243,249)
            shade='#'+''.join(f'{round(a+(b-a)*fraction):02x}' for a,b in zip(start,end))
            canvas.create_line(max(1,inset),y,size-max(1,inset),y,fill=shade)
    else:
        canvas.create_oval(1, 1, size-1, size-1, fill=bg, outline=bg)
    if kind == 'electric':
        canvas.create_polygon(*[v*s for v in (27,10,15,27,23,27,21,38,34,21,26,21)], fill=color, outline=color)
    elif kind == 'water':
        canvas.create_polygon(*[v*s for v in (24,10,14,25,14,31,18,36,24,38,30,36,34,31,34,25)], smooth=True, fill='', outline=color, width=2*s)
        line((19,29,20,32,24,34))
    elif kind == 'mail':
        rect((12,16,36,33)); line((12,17,24,26,36,17))
    elif kind == 'building':
        rect((14,11,34,37))
        for x in (19,28):
            for y in (17,24): canvas.create_rectangle(x*s,y*s,(x+2)*s,(y+2)*s,fill=color,outline=color)
        line((22,37,22,31,27,31,27,37))
    elif kind == 'sync':
        canvas.create_arc(12*s,12*s,36*s,36*s,start=35,extent=260,style='arc',outline=color,width=2*s)
        line((35,12,36,21,28,19))
    elif kind == 'log':
        rect((15,10,34,38)); line((20,18,29,18)); line((20,24,29,24));line((20,30,27,30))
    else:
        line((12,22,24,12,36,22));line((16,21,16,36,32,36,32,21));line((22,36,22,29,27,29,27,36))
    return canvas



class Panel(tk.Frame):
    """Native geometry instead of a canvas repaint for every Configure event."""
    def __init__(self,parent,height=None,padding=20,**kw):
        super().__init__(parent,bg=WHITE,highlightbackground=LINE,highlightthickness=1,**kw)
        self.body=tk.Frame(self,bg=WHITE,padx=padding,pady=padding)
        self.body.pack(fill='both',expand=True)


class ScrollPage:
    def __init__(self,parent,bg=BG):
        self.frame=tk.Frame(parent,bg=bg)
        self.canvas=tk.Canvas(self.frame,bg=bg,highlightthickness=0,yscrollincrement=24)
        bar=ttk.Scrollbar(self.frame,orient='vertical',command=self.canvas.yview)
        bar.pack(side='right',fill='y'); self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=bar.set)
        self.body=tk.Frame(self.canvas,bg=bg,padx=22,pady=20)
        self.item=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self._job=None; self._width=0; self._region=None; self.layout_count=0
        self.body.bind('<Configure>',self.schedule)
        self.canvas.bind('<Configure>',self.schedule)
    def schedule(self,event=None):
        if getattr(self.canvas._root(),'_ui_closing',False): return
        if event is not None and event.widget==self.canvas and event.width!=self._width:
            if self._job is not None: self.canvas.after_cancel(self._job)
            self._job=self.canvas.after(80,self.layout)
        elif self._job is None: self._job=self.canvas.after(24,self.layout)
    def layout(self):
        self._job=None
        if not self.canvas.winfo_exists(): return
        self.layout_count+=1
        width=self.canvas.winfo_width()
        if width!=self._width:
            self._width=width; self.canvas.itemconfigure(self.item,width=max(1,width))
        region=(0,0,width,self.body.winfo_reqheight())
        if region!=self._region:
            self._region=region; self.canvas.configure(scrollregion=region)


class Fold(tk.Frame):
    def __init__(self,parent,title):
        super().__init__(parent,bg=WHITE)
        self.opened=False; self.title=title
        self.button=ttk.Button(self,text='＋ '+title,style='Quiet.TButton',command=self.toggle)
        self.button.pack(anchor='w')
        self.body=tk.Frame(self,bg=WHITE,pady=10)
    def toggle(self):
        self.opened=not self.opened
        self.button.configure(text=('－ ' if self.opened else '＋ ')+self.title)
        if self.opened: self.body.pack(fill='x')
        else: self.body.pack_forget()


def section(parent,title):
    text(parent,title,11,INK,True).pack(anchor='w',pady=(0,12))


def field(parent,row,title,variable,password=False,choices=None):
    parent.columnconfigure(1,weight=1)
    text(parent,title,9,MUTED).grid(row=row,column=0,sticky='w',padx=(0,18),pady=7)
    w=ttk.Combobox(parent,textvariable=variable,values=choices,state='readonly') if choices else ttk.Entry(parent,textvariable=variable,show='●' if password else '')
    w.grid(row=row,column=1,sticky='ew',pady=7)
    return w


class DashboardUI:
    def __init__(self,app):
        self.app=app; self.root=app.root
        self.pages={}; self.nav={}; self.page='overview'
        self.last_refresh=0; self.last_log=None; self.last_action=None; self.last_connection_action=None
        self.proxy_badge=tk.StringVar(value='未连接微信')
        self.mail_badge=tk.StringVar(value='未开始监测')
        self.connection_detail=tk.StringVar()
        self.hint=tk.StringVar(value='连接微信 → 选择宿舍 → 查看余量')
        self.build()

    @staticmethod
    def set_if_changed(var,value):
        if var.get()!=value: var.set(value)

    def card(self,page,title=None):
        panel=Panel(page); panel.pack(fill='x',pady=(0,14))
        if title: section(panel.body,title)
        return panel.body

    def build(self):
        a=self.app
        header=tk.Frame(self.root,bg=WHITE,padx=22,pady=14); header.pack(fill='x')
        icon(header,'home',38).pack(side='left',padx=(0,10))
        text(header,'广东医 · 校园水电',16,INK,True).pack(side='left')
        text(header,'',9,BLUE,textvariable=self.mail_badge).pack(side='right')
        footer=tk.Frame(self.root,bg=WHITE,padx=22,pady=9); footer.pack(side='bottom',fill='x')
        self.save_button=ttk.Button(footer,text='保存监测设置',style='Primary.TButton',command=lambda:a.reminders.save_settings())
        self.footer_text=text(footer,'',9,MUTED,textvariable=a.status,wraplength=1600,anchor='w',justify='left')
        self.footer_text.pack(fill='x')
        shell=tk.Frame(self.root,bg=BG); shell.pack(fill='both',expand=True)
        sidebar=tk.Frame(shell,bg=WHITE,width=146); sidebar.pack(side='left',fill='y'); sidebar.pack_propagate(False)
        for key,label in (('overview','水电总览'),('login','微信连接'),('mail','监测设置'),('logs','运行记录')):
            button=ttk.Button(sidebar,text=label,style='Nav.TButton',command=lambda k=key:self.show(k))
            button.pack(fill='x',padx=8,pady=(16 if key=='overview' else 3,3)); self.nav[key]=button
        text(sidebar,'v1.7.1',8,MUTED).pack(side='bottom',anchor='w',padx=24,pady=18)
        self.content=ScrollPage(shell); self.content.frame.pack(side='left',fill='both',expand=True)
        a.canvas=self.content.canvas
        for key,title in (('overview','水电总览'),('login','微信连接'),('mail','监测设置'),('logs','运行记录')):
            page=tk.Frame(self.content.body,bg=BG); self.pages[key]=page
            text(page,title,21,INK,True).pack(anchor='w',pady=(0,18))
        self.build_overview(); self.build_logs()
        self.show('overview'); self.root.bind('<MouseWheel>',a.scroll)

    def build_overview(self):
        a=self.app; p=self.pages['overview']
        self.next_row=tk.Frame(p,bg=BLUE_LIGHT,padx=14,pady=10); self.next_row.pack(fill='x',pady=(0,14))
        text(self.next_row,'',9,BLUE,textvariable=self.hint,wraplength=600,justify='left').pack(side='left',fill='x',expand=True)
        self.login_link=ttk.Button(self.next_row,text='连接微信',style='Primary.TButton',command=lambda:self.show('login'))
        self.login_link.pack(side='right',padx=(10,0))
        b=self.card(p,'当前宿舍')
        selects=tk.Frame(b,bg=WHITE); selects.pack(fill='x'); a.combos=[]
        for col,title in enumerate(('校区','楼栋','房间')):
            selects.columnconfigure(col,weight=1,uniform='select')
            box=tk.Frame(selects,bg=WHITE); box.grid(row=0,column=col,sticky='ew',padx=(0 if col==0 else 10,0))
            text(box,title,9,MUTED).pack(anchor='w',pady=(0,6))
            combo=ttk.Combobox(box,state='disabled',width=10); combo.pack(fill='x'); a.combos.append(combo)
        a.campus_box,a.building_box,a.room_box=a.combos
        for box,callback in zip(a.combos,(a.choose_campus,a.choose_building,a.choose_room)): box.bind('<<ComboboxSelected>>',callback)
        self.room_detail=text(b,'',9,MUTED,textvariable=a.result_room,wraplength=900,justify='left')
        self.room_detail.pack(anchor='w',pady=(8,0))
        metrics=tk.Frame(p,bg=BG); metrics.pack(fill='x',pady=(0,12))
        self.metric_labels=[]
        for col,title,value,unit,kind in ((0,'剩余电量',a.electricity,'度','electric'),(1,'剩余水量',a.water,'吨','water')):
            metrics.columnconfigure(col,weight=1,uniform='metric')
            panel=Panel(metrics,padding=18); panel.grid(row=0,column=col,sticky='nsew',padx=(0,6) if col==0 else (6,0))
            row=tk.Frame(panel.body,bg=WHITE); row.pack(fill='x')
            text(row,title,10,MUTED).pack(side='left'); icon(row,kind,28).pack(side='right')
            row=tk.Frame(panel.body,bg=WHITE); row.pack(fill='x',pady=(8,0))
            label=text(row,'',34,BLUE,True,textvariable=value); label.pack(side='left')
            text(row,unit,10,MUTED).pack(side='right',anchor='s',pady=7)
            self.fit_metric(panel.body,label,value)
            self.metric_labels.append(label)
        text(p,'',9,MUTED,textvariable=a.updated).pack(anchor='w',pady=(0,12))
        row=tk.Frame(p,bg=BG); row.pack(fill='x',pady=(0,12))
        self.refresh_button=a.button(row,'刷新余量',a.query_selected); self.refresh_button.pack(side='left')
        self.monitor_button=ttk.Button(row,text='开始监测',style='Primary.TButton',command=self.toggle_monitor)
        self.monitor_button.pack(side='right')
        text(p,'',9,MUTED,textvariable=a.reminder_status,wraplength=900,justify='left').pack(anchor='w')

    def fit_metric(self,host,label,value):
        fonts={size:(FONT,size,'bold') for size in range(14,35,2)}
        state={'job':None,'key':None,'size':34}
        def apply():
            state['job']=None
            if not label.winfo_exists(): return
            key=(host.winfo_width(),value.get())
            if key==state['key']: return
            state['key']=key
            available=max(60,key[0]-46)
            size=next((s for s in sorted(fonts,reverse=True) if int(self.root.tk.call('font','measure',fonts[s],key[1]))<=available),14)
            if size!=state['size']:
                state['size']=size; label.configure(font=fonts[size])
        def schedule(*unused):
            if getattr(self.root,'_ui_closing',False): return
            if state['job']: label.after_cancel(state['job'])
            state['job']=label.after(70,apply)
        value.trace_add('write',schedule); host.bind('<Configure>',schedule,add='+')
        label._fonts=fonts

    def attach(self):
        self.build_login(); self.build_monitor(); self.refresh(force=True)

    def build_login(self):
        a=self.app; ctl=a.reminders; proxy=ctl.embedded; p=self.pages['login']
        b=self.card(p,'登录状态')
        text(b,'',11,BLUE,True,textvariable=self.proxy_badge).pack(anchor='w')
        text(b,'',9,MUTED,textvariable=proxy.status,wraplength=900,justify='left').pack(anchor='w',pady=(8,12))
        self.connect_button=ttk.Button(b,text='连接并获取登录',style='Primary.TButton',command=proxy.begin_login)
        self.connect_button.pack(anchor='w')
        text(b,'首次连接需确认安装证书和开启代理；登录成功后自动加载宿舍。',9,MUTED,wraplength=900,justify='left').pack(anchor='w',pady=(12,0))
        b=self.card(p,'小程序自动打开')
        row=tk.Frame(b,bg=WHITE); row.pack(fill='x')
        ttk.Entry(row,textvariable=ctl.vars['wechat_shortcut']).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='选择快捷方式',command=proxy.choose_shortcut).pack(side='right',padx=(8,0))
        ttk.Checkbutton(b,text='登录过期时自动打开小程序',variable=ctl.vars['wechat_auto_wake']).pack(anchor='w',pady=(10,0))
        ttk.Checkbutton(b,text='获取登录后关闭本次小程序窗口',variable=ctl.vars['wechat_close_after_token'],command=proxy.close_option_changed).pack(anchor='w')
        ttk.Button(b,text='保存连接设置',command=proxy.save).pack(anchor='w',pady=(12,0))
        b=self.card(p)
        advanced=Fold(b,'高级与故障处理'); advanced.pack(fill='x'); self.login_advanced=advanced
        b=advanced.body
        text(b,'手动 Token（粘贴后自动加载）',9,MUTED).pack(anchor='w')
        a.token_entry=ttk.Entry(b,textvariable=a.token,show='●'); a.token_entry.pack(fill='x',pady=(6,8))
        a.token_entry.bind('<KeyRelease>',a.token_changed)
        a.token_entry.bind('<<Paste>>',lambda e:a.root.after_idle(a.token_changed))
        a.show_token=tk.BooleanVar(value=False)
        row=tk.Frame(b,bg=WHITE); row.pack(fill='x')
        a.token_check=ttk.Checkbutton(row,text='显示 Token',variable=a.show_token,command=lambda:a.token_entry.configure(show='' if a.show_token.get() else '●')); a.token_check.pack(side='left')
        ttk.Button(row,text='清除凭证',style='Quiet.TButton',command=a.clear_token).pack(side='right')
        text(b,'',9,MUTED,textvariable=a.sync_status,wraplength=900,justify='left').pack(anchor='w',pady=10)
        row=tk.Frame(b,bg=WHITE); row.pack(fill='x')
        ttk.Button(row,text='重新加载宿舍',command=a.load_campuses).pack(side='left')
        ttk.Button(row,text='断开同步',command=proxy.disconnect).pack(side='left',padx=8)
        ttk.Button(row,text='恢复网络',command=proxy.recover).pack(side='left')
        row=tk.Frame(b,bg=WHITE); row.pack(fill='x',pady=(10,0))
        ttk.Button(row,text='绑定小程序窗口',command=proxy.choose_window).pack(side='left')
        ttk.Button(row,text='自动识别窗口',command=proxy.automatic_window).pack(side='left',padx=8)
        ttk.Button(row,text='移除证书',command=lambda:proxy.install_certificate(False)).pack(side='left')
        form=tk.Frame(b,bg=WHITE); form.pack(fill='x',pady=(12,0))
        field(form,0,'楼栋内部 ID',a.building_id); field(form,1,'房间内部 ID',a.room_id)
        ttk.Button(b,text='按内部编号查询',command=a.query_manual).pack(anchor='w',pady=(8,0))

    def build_monitor(self):
        a=self.app; ctl=a.reminders; p=self.pages['mail']; ctl.settings_widgets=[]
        b=self.card(p,'通知方式')
        for key,title in (('desktop_enabled','Windows 通知'),('desktop_each_query','每轮查询后显示水电余量'),('email_enabled','同时发送邮件')):
            w=ttk.Checkbutton(b,text=title,variable=ctl.vars[key],command=self.email_visibility if key=='email_enabled' else None)
            w.pack(anchor='w',pady=2); ctl.settings_widgets.append(w)
        ttk.Button(b,text='测试 Windows 通知',style='Quiet.TButton',command=ctl.test_desktop).pack(anchor='w',pady=(8,0))
        self.smtp_panel=Panel(p); b=self.smtp_panel.body
        section(b,'邮件服务')
        form=tk.Frame(b,bg=WHITE); form.pack(fill='x')
        for row,title,key in ((0,'SMTP 服务器','host'),(1,'端口','port'),(2,'加密方式','security'),(3,'登录邮箱','username'),(4,'密码 / 授权码','password'),(5,'发件人（可留空）','sender'),(6,'收件人（逗号分隔）','recipients')):
            w=field(form,row,title,ctl.password if key=='password' else ctl.vars[key],password=key=='password',choices=('SSL/TLS','STARTTLS') if key=='security' else None)
            ctl.settings_widgets.append(w)
            if key=='security': w.bind('<<ComboboxSelected>>',ctl.security_changed)
        ctl.test_button=ttk.Button(b,text='发送测试邮件',command=ctl.test_email); ctl.test_button.pack(anchor='w',pady=(10,0))
        b=self.card(p,'查询与提醒'); self.rules_panel=b.master
        form=tk.Frame(b,bg=WHITE); form.pack(fill='x')
        w=field(form,0,'查询间隔（分钟，至少 30）',ctl.vars['interval_minutes']); ctl.settings_widgets.append(w)
        w=ttk.Checkbutton(b,text='低余量时警告',variable=ctl.vars['threshold_enabled']); w.pack(anchor='w',pady=(12,2)); ctl.settings_widgets.append(w)
        form=tk.Frame(b,bg=WHITE); form.pack(fill='x')
        for row,title,key in ((0,'电量 ≤（度）','electricity_limit'),(1,'水量 ≤（吨）','water_limit'),(2,'持续不足重复提醒（小时）','repeat_hours')):
            ctl.settings_widgets.append(field(form,row,title,ctl.vars[key]))
        w=ttk.Checkbutton(b,text='每天固定时间提醒',variable=ctl.vars['daily_enabled']); w.pack(anchor='w',pady=(12,2)); ctl.settings_widgets.append(w)
        form=tk.Frame(b,bg=WHITE); form.pack(fill='x')
        ctl.settings_widgets.append(field(form,0,'时间（如 08:00, 20:00）',ctl.vars['daily_times']))
        b=self.card(p,'下次运行')
        ttk.Checkbutton(b,text='保存登录凭证和邮件授权码',variable=ctl.vars['remember_credentials'],command=ctl.remember_changed).pack(anchor='w')
        ttk.Checkbutton(b,text='打开软件后自动连接微信',variable=ctl.vars['proxy_auto_start']).pack(anchor='w',pady=3)
        ttk.Checkbutton(b,text='打开软件后自动开始监测',variable=ctl.vars['auto_start']).pack(anchor='w')
        text(b,'宿舍自动保存。退出或电脑休眠时，监测暂停。',9,MUTED,wraplength=900).pack(anchor='w',pady=(10,0))
        self.email_visibility()

    def email_visibility(self):
        if not hasattr(self,'smtp_panel'): return
        if self.app.reminders.vars['email_enabled'].get(): self.smtp_panel.pack(fill='x',pady=(0,14),before=self.rules_panel)
        else: self.smtp_panel.pack_forget()

    def build_logs(self):
        b=self.card(self.pages['logs'])
        self.log=tk.Text(b,height=20,wrap='word',font=(FONT,10),bg=WHITE,fg=MUTED,relief='flat',state='disabled')
        self.log.pack(fill='both',expand=True)

    def toggle_monitor(self):
        ctl=self.app.reminders
        if ctl.active or ctl.preflight_busy or ctl.desired_running: ctl.stop('监测已停止。')
        else: ctl.start()
        self.refresh(force=True)

    def show(self,key):
        if key not in self.pages: return
        for page in self.pages.values(): page.pack_forget()
        self.pages[key].pack(fill='both',expand=True)
        for name,button in self.nav.items(): button.configure(style='Selected.Nav.TButton' if name==key else 'Nav.TButton')
        self.page=key; self.content.canvas.yview_moveto(0); self.content.schedule()
        if key=='mail': self.save_button.pack(side='right',before=self.footer_text,padx=(10,0))
        else: self.save_button.pack_forget()
        if self.app.reminders: self.refresh(force=True)

    def refresh(self,force=False):
        ctl=self.app.reminders
        if not ctl: return
        now=time.monotonic()
        if not force and now-self.last_refresh<.4: return
        self.last_refresh=now
        state='监测中' if ctl.active else '等待微信登录' if ctl.waiting_for_token else '正在准备监测' if ctl.preflight_busy or ctl.desired_running else '未开始监测'
        self.set_if_changed(self.mail_badge,state)
        self.set_if_changed(self.proxy_badge,'微信同步已连接' if ctl.embedded.service.connected else '微信同步未连接')
        connection_action=('重新获取登录' if ctl.embedded.service.connected else '连接并获取登录','disabled' if ctl.embedded.busy else 'normal')
        if connection_action!=self.last_connection_action:
            self.last_connection_action=connection_action
            self.connect_button.configure(text=connection_action[0],state=connection_action[1])
        if self.app.selected_target(): self.room_detail.pack_forget()
        elif not self.room_detail.winfo_manager(): self.room_detail.pack(anchor='w',pady=(8,0))
        running=ctl.active or ctl.preflight_busy or ctl.desired_running
        action=('停止监测' if running else '开始监测', 'normal' if running or (self.app.flow_ready and not self.app.busy) else 'disabled')
        if action!=self.last_action:
            self.last_action=action; self.monitor_button.configure(text=action[0],state=action[1])
        hint='正在加载宿舍…' if self.app.busy else '选择校区、楼栋和房间后自动查询' if self.app.campuses and not self.app.flow_ready else '登录成功，宿舍已自动恢复' if self.app.flow_ready else '连接微信 → 选择宿舍 → 查看余量'
        self.set_if_changed(self.hint,hint)
        if self.app.flow_ready: self.next_row.pack_forget()
        elif not self.next_row.winfo_manager(): self.next_row.pack(fill='x',pady=(0,14),before=self.pages['overview'].winfo_children()[2])
        if self.page=='logs':
            logs='\n\n'.join(ctl.logs) or '暂无运行记录'
            if logs!=self.last_log:
                self.last_log=logs; self.log.configure(state='normal'); self.log.delete('1.0','end'); self.log.insert('end',logs); self.log.see('end'); self.log.configure(state='disabled')


def build_mail_dialog(ctl):
    ctl.app.ui.show('mail')


def build_proxy_dialog(panel):
    panel.ctl.app.ui.show('login')
