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
    label=tk.Label(parent, text=value, bg=parent.cget('bg'), fg=color,
                   font=(FONT, size, 'bold' if bold else 'normal'), **kw)
    if 'wraplength' in kw:
        preferred=kw['wraplength']
        def wrap(event):
            if not label.winfo_exists():return
            try:padding=int(parent.cget('padx'))*2
            except (ValueError,tk.TclError):padding=0
            label.configure(wraplength=max(80,min(preferred,event.width-padding)))
        parent.bind('<Configure>',wrap,add='+')
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


class Panel(tk.Canvas):
    def __init__(self, parent, height=None, padding=22, **kw):
        super().__init__(parent, bg=parent.cget('bg'), highlightthickness=0, **kw)
        self.body = tk.Frame(self, bg=WHITE, padx=max(0,padding-10), pady=max(0,padding-10))
        self.item = self.create_window(0, 0, anchor='nw', window=self.body)
        self.fixed_height = height
        self.bind('<Configure>', self.layout)
        self.body.bind('<Configure>', self.layout)
    def layout(self, event=None):
        width = max(1, self.winfo_width())
        height = self.fixed_height or self.body.winfo_reqheight()+20
        self.configure(height=height)
        self.itemconfigure(self.item, width=max(1,width-20))
        self.coords(self.item,10,10)
        self.delete('panel-outline')
        r=14
        self.create_polygon(0,r,0,0,r,0,width-r,0,width,0,width,r,width,height-r,width,height,width-r,height,r,height,0,height,0,height-r,
                            smooth=True,fill=WHITE,outline=LINE,tags='panel-outline')
        self.tag_lower('panel-outline')


def section(parent, title, subtitle=None):
    frame=tk.Frame(parent,bg=WHITE)
    frame.pack(fill='x',pady=(0,16))
    text(frame,title,12,BLUE,True).pack(anchor='w')
    if subtitle:text(frame,subtitle,9,MUTED,wraplength=700,justify='left').pack(anchor='w',pady=(5,0))
    return frame


class ScrollPage:
    def __init__(self, parent, bg=WHITE):
        self.frame=tk.Frame(parent,bg=bg)
        self.canvas=tk.Canvas(self.frame,bg=bg,highlightthickness=0)
        bar=ttk.Scrollbar(self.frame,orient='vertical',command=self.canvas.yview)
        bar.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=bar.set)
        self.body=tk.Frame(self.canvas,bg=bg,padx=24,pady=20)
        self.item=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.item,width=e.width))


class DashboardUI:
    def __init__(self, app):
        self.app=app;self.root=app.root
        self.pages={};self.nav={};self.page='overview';self.last_log=None;self.last_refresh=0
        self.proxy_badge=tk.StringVar(self.root,value='微信同步 · 未接入')
        self.mail_badge=tk.StringVar(self.root,value='持续监测 · 未启动')
        self.mail_summary=tk.StringVar(self.root)
        self.rule_summary=tk.StringVar(self.root)
        self.daily_summary=tk.StringVar(self.root)
        self.close_summary=tk.StringVar(self.root)
        self.hint=tk.StringVar(self.root,value='首次使用：先在“登录与同步”中接入微信，再加载宿舍列表。')
        self.build()

    def build(self):
        a=self.app
        header=tk.Frame(self.root,bg=WHITE,padx=24,pady=12)
        header.pack(fill='x')
        mark=icon(header,'home',48);mark.pack(side='left',padx=(0,12))
        brand=tk.Frame(header,bg=WHITE);brand.pack(side='left')
        text(brand,'广东医 · 校园水电',17,INK,True).pack(anchor='w')
        text(brand,'宿舍余量查询与桌面提醒',9,MUTED).pack(anchor='w',pady=(3,0))
        states=tk.Frame(header,bg=WHITE);states.pack(side='right')
        text(states,'',9,BLUE,textvariable=self.proxy_badge).pack(anchor='e')
        text(states,'',9,MUTED,textvariable=self.mail_badge).pack(anchor='e',pady=(5,0))
        tk.Frame(self.root,bg=LINE,height=1).pack(fill='x')
        footer=tk.Frame(self.root,bg=WHITE,padx=20,pady=9)
        footer.pack(side='bottom',fill='x')
        text(footer,'状态',9,BLUE,True).pack(side='left',padx=(0,12))
        self.footer_text=text(footer,'',9,MUTED,textvariable=a.status,anchor='w',justify='left',wraplength=800,height=2)
        self.footer_text.pack(fill='x',expand=True)
        shell=tk.Frame(self.root,bg=BG);shell.pack(fill='both',expand=True)
        sidebar=tk.Frame(shell,bg=WHITE,width=164)
        sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
        text(sidebar,'校园服务',9,MUTED).pack(anchor='w',padx=20,pady=(24,10))
        for key,label in (('overview','水电总览'),('login','登录与同步'),('mail','监测与提醒'),('logs','运行记录')):
            btn=ttk.Button(sidebar,text=label,style='Nav.TButton',command=lambda k=key:self.show(k))
            btn.pack(fill='x',padx=10,pady=3);self.nav[key]=btn
        text(sidebar,'个人查询工具 · v1.6.0\n数据以缴费系统为准',8,MUTED,justify='left').pack(side='bottom',anchor='w',padx=20,pady=22)
        content=ScrollPage(shell,BG);content.frame.pack(side='left',fill='both',expand=True)
        self.content=content;a.canvas=content.canvas
        self.content.body.configure(padx=24,pady=23)
        self.content.frame.bind('<Configure>',lambda e:self.footer_text.configure(wraplength=max(520,e.width-40)))
        for key,title,subtitle in (
            ('overview','水电总览','查看当前宿舍的水电余量，及时安排充值。'),
            ('login','登录与同步','连接真实微信登录，自动接入新的查询凭证。'),
            ('mail','监测与提醒','不配置邮箱也能持续监测，用 Windows 通知查看水电余量。'),
            ('logs','运行记录','查看查询、登录同步与邮件提醒的处理结果。')):
            page=tk.Frame(content.body,bg=BG);self.pages[key]=page
            text(page,title,21,INK,True).pack(anchor='w')
            text(page,subtitle,10,MUTED).pack(anchor='w',pady=(6,14))
        self.build_overview();self.build_login();self.build_mail();self.build_logs()
        self.show('overview')
        self.root.bind('<MouseWheel>',a.scroll)

    def heading(self,parent,title,icon_name=None):
        row=tk.Frame(parent,bg=WHITE);row.pack(fill='x',pady=(0,16))
        if icon_name:icon(row,icon_name,30).pack(side='left',padx=(0,9))
        text(row,title,11,INK,True).pack(side='left')
        return row

    def build_overview(self):
        a=self.app;p=self.pages['overview']
        text(p,'',9,BLUE,textvariable=self.hint,wraplength=740,justify='left').pack(anchor='w',pady=(0,14))
        room=tk.Frame(p,bg=BG);room.pack(fill='x',pady=(0,12))
        text(room,'',11,INK,True,textvariable=a.result_room,wraplength=700,justify='left').pack(anchor='w')
        metrics=tk.Frame(p,bg=BG);metrics.pack(fill='x')
        for col,title,value,unit,kind in ((0,'剩余电量',a.electricity,'度','electric'),(1,'剩余水量',a.water,'吨','water')):
            metrics.columnconfigure(col,weight=1,uniform='metric')
            card=Panel(metrics,height=153);card.grid(row=0,column=col,sticky='ew',padx=(0,8) if col==0 else (8,0))
            top=tk.Frame(card.body,bg=WHITE);top.pack(fill='x')
            text(top,title,10,MUTED).pack(side='left');icon(top,kind,35).pack(side='right')
            line=tk.Frame(card.body,bg=WHITE);line.pack(anchor='w',pady=(4,4))
            label=text(line,'',38,BLUE,True,textvariable=value);label.pack(side='left')
            text(line,unit,11,MUTED).pack(side='left',padx=(9,0),pady=(22,0))
            def fit(*unused,v=value,w=label,host=card.body):
                available=max(80,host.winfo_width()-70)
                size=38
                while size>12 and int(self.root.tk.call('font','measure',(FONT,size,'bold'),v.get()))>available:
                    size-=1
                w.configure(font=(FONT,size,'bold'))
            value.trace_add('write',fit)
            card.body.bind('<Configure>',fit,add='+')
        text(p,'',8,MUTED,textvariable=a.updated,wraplength=720,justify='left').pack(anchor='w',pady=(10,18))
        select=Panel(p);select.pack(fill='x',pady=(0,16));b=select.body
        row=self.heading(b,'选择宿舍','building')
        a.button(row,'查询所选宿舍',a.query_selected,primary=True).pack(side='right')
        a.button(row,'加载宿舍列表',a.load_campuses).pack(side='right',padx=(0,8))
        selects=tk.Frame(b,bg=WHITE);selects.pack(fill='x');a.combos=[]
        for col,title in enumerate(('校区','楼栋','房间')):
            selects.columnconfigure(col,weight=1,uniform='select')
            block=tk.Frame(selects,bg=WHITE);block.grid(row=0,column=col,sticky='ew',padx=(0 if col==0 else 12,0))
            text(block,title,9,MUTED).pack(anchor='w',pady=(0,7))
            combo=ttk.Combobox(block,state='disabled',width=12);combo.pack(fill='x');a.combos.append(combo)
        a.campus_box,a.building_box,a.room_box=a.combos
        for box,callback in zip(a.combos,(a.choose_campus,a.choose_building,a.choose_room)):box.bind('<<ComboboxSelected>>',callback)
        shortcuts=Panel(p);shortcuts.pack(fill='x',pady=(0,16));b=shortcuts.body
        self.heading(b,'常用服务')
        grid=tk.Frame(b,bg=WHITE);grid.pack(fill='x')
        for col,title,kind,command in ((0,'微信同步','sync',lambda:self.app.reminders.embedded.open()),(1,'监测设置','mail',lambda:self.app.reminders.open()),(2,'运行记录','log',lambda:self.show('logs')),(3,'开始监测','building',lambda:self.app.reminders.start())):
            grid.columnconfigure(col,weight=1,uniform='shortcut')
            item=tk.Frame(grid,bg=WHITE);item.grid(row=0,column=col,sticky='ew')
            icon(item,kind,44,tile=True).pack()
            ttk.Button(item,text=title,style='Quiet.TButton',command=command).pack(pady=(5,0))
        status=tk.Frame(p,bg=BG);status.pack(fill='x')
        text(status,'电余量每半小时更新；水余量每天 14:00 更新，以小程序说明为准。',8,MUTED,wraplength=700,justify='left').pack(anchor='w')

    def build_manual(self,p):
        a=self.app
        manual=Panel(p);manual.pack(fill='x');b=manual.body
        self.heading(b,'按内部编号查询')
        row=tk.Frame(b,bg=WHITE);row.pack(fill='x')
        for title,var in (('楼栋 ID',a.building_id),('房间 ID',a.room_id)):
            text(row,title,9,MUTED).pack(side='left',padx=(0,6))
            field=ttk.Entry(row,textvariable=var,width=9);field.pack(side='left',padx=(0,16));a.editable.append(field)
        a.button(row,'查询',a.query_manual).pack(side='right')
        text(b,'填写系统内部编号；楼号和门牌号不一定是内部 ID。',8,MUTED).pack(anchor='w',pady=(12,0))

    def state_row(self,parent,title,detail,command):
        row=tk.Frame(parent,bg=WHITE);row.pack(fill='x')
        label=text(row,'',10,BLUE,True,textvariable=title);label.pack(side='left')
        ttk.Button(row,text='查看设置',style='Quiet.TButton',command=command).pack(side='right')
        text(parent,'',9,MUTED,textvariable=detail,wraplength=640,justify='left').pack(anchor='w',pady=(3,0))

    def build_login(self):
        a=self.app;p=self.pages['login']
        panel=Panel(p);panel.pack(fill='x',pady=(0,16));b=panel.body
        self.heading(b,'微信登录同步','sync')
        text(b,'微信小程序返回可用 Token 后，软件会验证并接入。',10,MUTED,wraplength=620).pack(anchor='w')
        row=tk.Frame(b,bg=WHITE);row.pack(fill='x',pady=(16,12))
        a.sync_check=ttk.Checkbutton(row,text='接收新的登录 Token',command=lambda:a.reminders.sync_changed());a.sync_check.pack(side='left')
        ttk.Button(row,text='内置同步设置',style='Primary.TButton',command=lambda:a.reminders.embedded.open()).pack(side='right')
        text(b,'',9,MUTED,textvariable=a.sync_status,wraplength=650,justify='left').pack(anchor='w')
        text(b,'',9,BLUE,textvariable=self.close_summary,wraplength=650).pack(anchor='w',pady=(12,0))
        ttk.Button(b,text='查看接入说明',style='Quiet.TButton',command=lambda:a.reminders.show_sync_help()).pack(anchor='w',pady=(9,0))
        panel=Panel(p);panel.pack(fill='x');b=panel.body
        self.heading(b,'登录凭证')
        text(b,'可手动填写自己的 Token；保存凭证选项位于监测设置。',9,MUTED,wraplength=640).pack(anchor='w',pady=(0,14))
        a.token_entry=ttk.Entry(b,textvariable=a.token,show='●');a.token_entry.pack(fill='x');a.editable.append(a.token_entry)
        a.token_entry.bind('<KeyRelease>',a.token_changed)
        a.token_entry.bind('<<Paste>>',lambda e:a.root.after_idle(a.token_changed))
        a.show_token=tk.BooleanVar(value=False)
        row=tk.Frame(b,bg=WHITE);row.pack(fill='x',pady=(14,0))
        a.token_check=ttk.Checkbutton(row,text='显示 Token',variable=a.show_token,command=lambda:a.token_entry.configure(show='' if a.show_token.get() else '●'))
        a.token_check.pack(side='left')
        a.button(row,'保存设置',lambda:a.reminders.save_settings()).pack(side='right')
        a.button(row,'清空',a.clear_token).pack(side='right',padx=8)
        spacer=tk.Frame(p,bg=BG,height=16);spacer.pack()
        self.build_manual(p)

    def build_mail(self):
        a=self.app;p=self.pages['mail']
        panel=Panel(p);panel.pack(fill='x',pady=(0,16));b=panel.body
        self.heading(b,'提醒服务','mail')
        text(b,'',12,BLUE,True,textvariable=self.mail_badge).pack(anchor='w')
        text(b,'',10,MUTED,textvariable=a.reminder_status,wraplength=650,justify='left').pack(anchor='w',pady=(8,16))
        row=tk.Frame(b,bg=WHITE);row.pack(fill='x')
        ttk.Button(row,text='开始监测',style='Primary.TButton',command=lambda:a.reminders.start()).pack(side='left')
        ttk.Button(row,text='停止监测',command=lambda:a.reminders.stop()).pack(side='left',padx=8)
        ttk.Button(row,text='通知与监测设置',command=lambda:a.reminders.open()).pack(side='right')
        panel=Panel(p);panel.pack(fill='x');b=panel.body
        self.heading(b,'当前提醒规则')
        for title,var in (('固定时间',self.daily_summary),('低余量提醒',self.rule_summary),('邮件服务',self.mail_summary)):
            text(b,title,10,INK,True).pack(anchor='w',pady=(8,5))
            text(b,'',10,MUTED,textvariable=var,wraplength=660,justify='left').pack(anchor='w',pady=(0,14))
        tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=(0,14))
        text(b,'程序保持运行且电脑不休眠时，才能执行查询和发送提醒。',9,MUTED,wraplength=660).pack(anchor='w')

    def build_logs(self):
        p=self.pages['logs'];panel=Panel(p);panel.pack(fill='x');b=panel.body
        self.heading(b,'最近处理记录','log')
        self.log=tk.Text(b,height=20,wrap='word',font=(FONT,10),bg=WHITE,fg=MUTED,relief='flat',padx=0,pady=6,
                         selectbackground=BLUE_LIGHT,selectforeground=INK)
        self.log.pack(fill='both',expand=True);self.log.configure(state='disabled')

    def show(self,key):
        for page in self.pages.values():page.pack_forget()
        self.pages[key].pack(fill='both',expand=True)
        for name,button in self.nav.items():button.configure(style='Selected.Nav.TButton' if name==key else 'Nav.TButton')
        self.page=key;self.content.canvas.yview_moveto(0)

    def refresh(self):
        ctl=self.app.reminders
        if not ctl:return
        now=time.monotonic()
        if now-self.last_refresh<.5:return
        self.last_refresh=now
        connected=ctl.embedded.service.connected
        self.proxy_badge.set('微信同步 · '+('已接入' if connected else '未接入'))
        self.mail_badge.set('持续监测 · '+('监测中' if ctl.active else '等待新 Token' if ctl.waiting_for_token else '校验中' if ctl.preflight_busy else '未启动'))
        values=ctl.values()
        self.daily_summary.set(('每天 '+values['daily_times']+'（北京时间）') if values['daily_enabled'] else '未开启固定时间提醒')
        self.rule_summary.set(('电量 ≤ '+(values['electricity_limit'] or '未设置')+' 度  /  水量 ≤ '+(values['water_limit'] or '未设置')+' 吨\n每 '+values['interval_minutes']+' 分钟查询；持续不足每 '+values['repeat_hours']+' 小时提醒') if values['threshold_enabled'] else '未开启低余量提醒')
        self.mail_summary.set(('Windows 桌面通知：'+('开启' if values['desktop_enabled'] else '关闭')+'；邮件：'+('已启用 '+values['host'] if values['email_enabled'] else '关闭（无需配置邮箱）')))
        self.close_summary.set('同步后关闭小程序：'+('已开启，验证成功后延时 3 秒关闭' if values['wechat_close_after_token'] else '已关闭'))
        self.hint.set('选择宿舍后可开始持续监测，最低每 30 分钟检查一次；邮箱为可选项。' if self.app.token.get().strip() else '首次使用：先在“登录与同步”中接入微信，再加载宿舍列表。')
        logs='\n\n'.join(ctl.logs) or '暂无运行记录。查询、同步与邮件提醒的结果会显示在这里。'
        if logs!=self.last_log:
            self.last_log=logs;self.log.configure(state='normal');self.log.delete('1.0','end');self.log.insert('end',logs);self.log.see('end');self.log.configure(state='disabled')


class TabHost(tk.Frame):
    """Flat blue-underlined tabs; each page retains normal keyboard controls."""
    def __init__(self,parent):
        super().__init__(parent,bg=WHITE)
        self.bar=tk.Frame(self,bg=WHITE);self.bar.pack(fill='x',pady=(0,10))
        self.tabs=[];self.current=0
    def add(self,page,text):
        index=len(self.tabs)
        item=tk.Frame(self.bar,bg=WHITE);item.pack(side='left')
        button=ttk.Button(item,text=text,style='Tab.TButton',command=lambda:self.show(index))
        button.pack()
        underline=tk.Frame(item,bg=WHITE,height=3);underline.pack(fill='x',padx=20)
        button.bind('<Left>',lambda e:self.show((index-1)%len(self.tabs)))
        button.bind('<Right>',lambda e:self.show((index+1)%len(self.tabs)))
        self.tabs.append((page,button,underline))
        if len(self.tabs)==1:self.show(0)
    def show(self,index):
        for i,(page,button,line) in enumerate(self.tabs):
            page.pack_forget()
            button.configure(style='Selected.Tab.TButton' if i==index else 'Tab.TButton')
            line.configure(bg=BLUE if i==index else WHITE)
        self.tabs[index][0].pack(fill='both',expand=True)
        self.current=index
    def index(self,key):
        return self.current if key=='current' else int(key)


def dialog_shell(root,title,subtitle,tab_names):
    win=tk.Toplevel(root);win.title(title)
    win.geometry(f'890x{max(600,min(790,root.winfo_screenheight()-100))}')
    win.minsize(740,600);win.configure(bg=WHITE)
    header=tk.Frame(win,bg=WHITE,padx=24,pady=20);header.pack(fill='x')
    text(header,title,19,INK,True).pack(anchor='w')
    text(header,subtitle,9,MUTED,wraplength=780,justify='left').pack(anchor='w',pady=(6,0))
    tk.Frame(win,bg=LINE,height=1).pack(fill='x')
    footer=tk.Frame(win,bg=WHITE,padx=22,pady=14);footer.pack(side='bottom',fill='x')
    notebook=TabHost(win);notebook.pack(fill='both',expand=True,padx=18,pady=(6,0))
    pages=[]
    for name in tab_names:
        page=ScrollPage(notebook);notebook.add(page.frame,text=name);pages.append(page)
    def scroll(event):
        if event.delta and not isinstance(event.widget,ttk.Combobox):
            selected=notebook.index('current')
            pages[selected].canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
    win.bind('<MouseWheel>',scroll)
    return win,footer,[page.body for page in pages],notebook


def field(parent,row,title,variable,controller=None,password=False,choices=None):
    parent.columnconfigure(1,weight=1)
    text(parent,title,10,MUTED).grid(row=row,column=0,sticky='w',padx=(0,24),pady=9)
    widget=ttk.Combobox(parent,textvariable=variable,values=choices,state='readonly') if choices else ttk.Entry(parent,textvariable=variable,show='●' if password else '')
    widget.grid(row=row,column=1,sticky='ew',pady=9)
    if controller:controller.settings_widgets.append(widget)
    return widget


def hint(parent,value,pady=12):
    text(parent,value,9,MUTED,wraplength=700,justify='left').pack(anchor='w',pady=(pady,0))


def build_mail_dialog(ctl):
    win,footer,pages,book=dialog_shell(ctl.root,'监测与提醒设置','独立持续监测，Windows 通知与邮件可分别开启。最低查询间隔为 30 分钟。',
                                     ('通知方式','提醒规则','邮件服务','启动与保存','运行记录'))
    ctl.dialog=win;ctl.settings_widgets=[]
    win.protocol('WM_DELETE_WINDOW',ctl.close_dialog)
    ttk.Button(footer,text='保存设置',style='Primary.TButton',command=ctl.save_settings).pack(side='right')
    ttk.Button(footer,text='测试桌面通知',command=ctl.test_desktop).pack(side='right',padx=10)
    ttk.Button(footer,text='开始监测',command=ctl.start).pack(side='left')
    ttk.Button(footer,text='停止监测',style='Quiet.TButton',command=ctl.stop).pack(side='left',padx=8)
    b=pages[0]
    section(b,'Windows 桌面通知','无需邮箱、账号或授权码。收到通知时会显示当前宿舍的电量和水量。')
    for key,title in (('desktop_enabled','启用 Windows 桌面通知'),('desktop_each_query','每轮成功查询后通知水电余量'),('email_enabled','同时启用邮件提醒（可选，需配置 SMTP）')):
        check=ttk.Checkbutton(b,text=title,variable=ctl.vars[key]);check.pack(anchor='w',pady=8);ctl.settings_widgets.append(check)
    hint(b,'低阈值、固定时间通知使用“提醒规则”页的设置。\n达到低阈值时，同一条余量通知升级为警告，不重复弹两条。\n\nWindows 免打扰或关闭通知可能阻止横幅。\n“已提交”只代表系统接受通知请求；最小化程序可继续监测。\n关闭程序或休眠会停止运行。')
    b=pages[2]
    section(b,'SMTP 邮件服务','填写邮箱服务商提供的 SMTP 地址和授权码，再发送测试邮件。')
    form=tk.Frame(b,bg=WHITE);form.pack(fill='x')
    for row,title,key in ((0,'SMTP 服务器','host'),(1,'端口','port'),(2,'连接加密','security'),(3,'登录账号','username'),(4,'密码 / 授权码','password'),(5,'发件人邮箱','sender'),(6,'收件人邮箱','recipients')):
        widget=field(form,row,title,ctl.password if key=='password' else ctl.vars[key],ctl,password=key=='password',choices=('SSL/TLS','STARTTLS') if key=='security' else None)
        if key=='security':widget.bind('<<ComboboxSelected>>',ctl.security_changed)
    hint(b,'发件人留空时使用登录账号；多个收件人用逗号分隔。\n常见端口：SSL/TLS 465，STARTTLS 587，以服务商说明为准。')
    ctl.test_button=ttk.Button(b,text='发送测试邮件',command=ctl.test_email);ctl.test_button.pack(anchor='w',pady=14)
    b=pages[1]
    section(b,'提醒规则','规则按北京时间执行；水、电阈值分别判断。')
    check=ttk.Checkbutton(b,text='每天固定时间发送余量通知',variable=ctl.vars['daily_enabled']);check.pack(anchor='w');ctl.settings_widgets.append(check)
    form=tk.Frame(b,bg=WHITE);form.pack(fill='x',pady=(0,16))
    field(form,0,'每天发送时间',ctl.vars['daily_times'],ctl)
    hint(b,'使用 HH:MM，多个时间用逗号分隔，如 08:00, 20:00。',0)
    tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=18)
    check=ttk.Checkbutton(b,text='低余量时发送警告',variable=ctl.vars['threshold_enabled']);check.pack(anchor='w');ctl.settings_widgets.append(check)
    form=tk.Frame(b,bg=WHITE);form.pack(fill='x')
    for row,title,key in ((0,'电量 ≤（度）','electricity_limit'),(1,'水量 ≤（吨）','water_limit'),(2,'查询间隔（分钟，最低 30）','interval_minutes'),(3,'持续不足重复提醒（小时）','repeat_hours')):
        field(form,row,title,ctl.vars[key],ctl)
    hint(b,'阈值留空表示不监测该项；首次低于阈值时提醒，持续不足按间隔重复。充值恢复后可重新触发。')
    hint(b,'自动查询和失败后的重试至少间隔 30 分钟；固定时间在两轮查询之间到达时，使用上一次成功读数并标注查询时间。关闭这两项规则仍可持续监测。')
    b=pages[3]
    section(b,'启动与保存','设置保存在当前软件目录，无需重新填写。')
    ttk.Checkbutton(b,text='保存 Token 和 SMTP 密码 / 授权码',variable=ctl.vars['remember_credentials'],command=ctl.remember_changed).pack(anchor='w',pady=6)
    ttk.Checkbutton(b,text='启动软件后自动开始提醒',variable=ctl.vars['auto_start']).pack(anchor='w',pady=6)
    hint(b,'自动开始前验证 Token；只有启用邮件时才检查 SMTP。未配置邮箱也可自动开始监测。\n此选项不会设置 Windows 开机启动。')
    tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=20)
    ttk.Checkbutton(b,text='接收小程序登录响应，自动同步 Token',variable=ctl.vars['token_sync_enabled'],command=ctl.sync_changed).pack(anchor='w')
    ttk.Button(b,text='打开微信同步设置',command=ctl.embedded.open).pack(anchor='w',pady=14)
    hint(b,'保存凭证后，.env 包含明文 Token 和 SMTP 授权码，请勿分享。\n程序关闭或电脑休眠时，无法执行查询和邮件发送。')
    ttk.Button(b,text='打开配置文件夹',style='Quiet.TButton',command=ctl.open_directory).pack(anchor='w',pady=14)
    b=pages[4];section(b,'运行记录','最近的验证、查询与通知处理结果。')
    ctl.log_widget=tk.Text(b,height=22,wrap='word',font=(FONT,10),bg=WHITE,fg=MUTED,relief='flat')
    ctl.log_widget.pack(fill='both',expand=True)
    ctl.log_widget.insert('end','\n'.join(ctl.logs) or '暂无处理记录，可先发送测试邮件验证配置。')
    ctl.log_widget.configure(state='disabled')
    ctl.lock_settings(ctl.active or ctl.preflight_busy)
    ctl.test_button.configure(state='disabled' if ctl.test_busy else 'normal')


def build_proxy_dialog(panel):
    ctl=panel.ctl
    win,footer,pages,book=dialog_shell(panel.root,'微信同步设置','在软件内接收真实小程序的登录响应，验证成功后接续监测。',
                                     ('同步接入','微信与窗口','启动与运行'))
    panel.dialog=win
    ttk.Button(footer,text='保存设置',style='Primary.TButton',command=panel.save).pack(side='right')
    ttk.Button(footer,text='关闭接入',command=panel.disconnect).pack(side='left')
    ttk.Button(footer,text='恢复网络',style='Quiet.TButton',command=panel.recover).pack(side='left',padx=8)
    b=pages[0];section(b,'首次接入','按顺序准备引擎、安装专用证书，然后开启同步。')
    grid=tk.Frame(b,bg=WHITE);grid.pack(fill='x')
    for col,num,title,desc,command in ((0,'01','准备引擎','生成当前软件目录的专用证书。',panel.prepare),(1,'02','安装证书','安装到当前用户的根证书存储。',panel.install_certificate),(2,'03','开启同步','接入本地代理，等待登录响应。',panel.connect)):
        grid.columnconfigure(col,weight=1,uniform='step')
        item=tk.Frame(grid,bg=WHITE,padx=12);item.grid(row=0,column=col,sticky='nsew')
        text(item,num,23,BLUE,True).pack(anchor='w');text(item,title,11,INK,True).pack(anchor='w',pady=(8,5))
        text(item,desc,9,MUTED,wraplength=195,justify='left',height=3).pack(anchor='w')
        ttk.Button(item,text=title,command=command).pack(anchor='w',pady=12)
    tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=18)
    text(b,'',10,BLUE,textvariable=panel.status,wraplength=700,justify='left').pack(anchor='w')
    hint(b,'开启后，在微信中打开广东医缴费并进入查询页。新 Token 通过余量查询验证后才会接入；唤起窗口本身不代表登录成功。')
    hint(b,'接入期间，使用系统代理的应用流量经过本地引擎。只解密学校缴费域名，其他域名透传；关闭接入或退出软件时恢复原代理。')
    ttk.Button(b,text='移除本软件证书',style='Quiet.TButton',command=lambda:panel.install_certificate(False)).pack(anchor='w',pady=16)
    b=pages[1];section(b,'小程序唤起','选择微信为广东医缴费创建的桌面快捷方式。')
    ttk.Checkbutton(b,text='Token 失效时通过快捷方式唤起小程序',variable=ctl.vars['wechat_auto_wake']).pack(anchor='w',pady=(0,12))
    ttk.Entry(b,textvariable=ctl.vars['wechat_shortcut']).pack(fill='x')
    row=tk.Frame(b,bg=WHITE);row.pack(fill='x',pady=12)
    ttk.Button(row,text='选择快捷方式',command=panel.choose_shortcut).pack(side='left')
    ttk.Button(row,text='测试唤起',command=panel.test_wake).pack(side='left',padx=8)
    tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=18)
    section(b,'同步后的窗口处理')
    ttk.Checkbutton(b,text='Token 验证成功 3 秒后关闭本轮小程序窗口',variable=ctl.vars['wechat_close_after_token'],command=panel.close_option_changed).pack(anchor='w')
    hint(b,'默认识别唯一的“广东医缴费”窗口。识别不到时，先打开目标小程序，再选择窗口绑定。只关闭本软件这一轮唤起的窗口。')
    row=tk.Frame(b,bg=WHITE);row.pack(fill='x',pady=14)
    ttk.Button(row,text='选择小程序窗口',command=panel.choose_window).pack(side='left')
    ttk.Button(row,text='恢复自动识别',style='Quiet.TButton',command=panel.automatic_window).pack(side='left',padx=8)
    form=tk.Frame(b,bg=WHITE);form.pack(fill='x')
    widget=field(form,0,'已绑定窗口',ctl.vars['wechat_window_title']);widget.configure(state='readonly')
    hint(b,'空白表示自动识别。未产生登录响应或 Token 验证失败时，窗口保持打开。\n微信版本如果不支持创建快捷方式，可以手动打开小程序；本版不自动点击小程序内部页面。')
    b=pages[2];section(b,'启动与运行','软件开启后，可按已保存的设置接入同步。')
    ttk.Checkbutton(b,text='启动软件后自动开启内置同步',variable=ctl.vars['proxy_auto_start']).pack(anchor='w',pady=8)
    hint(b,'需先安装证书并保存设置。此选项会接入当前用户系统代理；检测到其他系统代理或 PAC 时暂停接入。')
    tk.Frame(b,bg=LINE,height=1).pack(fill='x',pady=20)
    section(b,'本地数据与恢复')
    hint(b,'引擎仅监听 127.0.0.1:18765，仅解密 pay.gdmu.edu.cn:443。\n\n'
           'data/https-proxy 包含本目录证书和私钥；.env 可能包含凭证。不要分享这些运行数据。\n\n'
           '软件异常退出后，下次启动会检查代理恢复记录。若代理已被其他程序修改，本软件不会强行覆盖。\n\n'
           '同步开启后没有响应时，可关闭小程序窗口再重新打开，让微信重新建立连接。',0)
