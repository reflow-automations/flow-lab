"""Native Windows management window. Uses the existing loopback API, no browser."""
from datetime import datetime
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk,messagebox,filedialog
import json
from pathlib import Path
from urllib.parse import urlencode,quote
import httpx
from shortcut_config import shortcut,shortcut_label,KEYS,MODIFIERS,LABELS
from model_guide import load_guide,guide_text
from openrouter_guide import model_choices,SUGGESTIONS,LIMITS as ROUTER_GUIDE_LIMITS
from PIL import Image,ImageTk

# Reflow palette (branding/brand-guide.md) with the Flow Lab app surfaces.
PAGE='#F3F6F4';CARD='#FFFFFF';LINE='#DCE5E0';NAVY='#131C2B';MUTED='#5E6E67'
GREEN='#13A47C';GREEN_DARK='#0F8A68';GREEN_SOFT='#E7F7F1';ORANGE='#F5981B';WARN='#8A5E00'

# Sidebar: panel key, label, Segoe Fluent/MDL2 glyph. A gap separates daily use from configuration.
NAV=[('home','Dicteren',''),('history','Geschiedenis',''),('dictionary','Woordenboek',''),
     ('snippets','Snippets',''),('learning','Geleerd',''),None,
     ('settings','Instellingen',''),('openrouter','OpenRouter','')]

def entry_payload(kind,identifier,name,value,aliases,enabled):
    return dict(id=identifier or None,name=name if kind=='snippet' else value,
                value=value,aliases=[a.strip() for a in aliases.splitlines() if a.strip()],enabled=bool(enabled))

def phone_library(data):
    """Library in the Android import format. Wispr spelling hints are skipped: the phone ignores them."""
    keep=('name','value','aliases','enabled','source')
    return {kind:[{k:row[k] for k in keep if k in row} for row in data.get(kind,[]) if row.get('source')!='wispr-hint']
            for kind in ('dictionary','snippets')}

def set_text(widget,value):
    widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value)

def text_box(parent,height,size=11):
    """Plain white text area with a thin border, matching the cards."""
    return tk.Text(parent,height=height,wrap='word',font=('Segoe UI',size),padx=12,pady=10,relief='flat',borderwidth=0,
                   background=CARD,foreground=NAVY,insertbackground=NAVY,selectbackground=GREEN_SOFT,selectforeground=NAVY,
                   highlightthickness=1,highlightbackground=LINE,highlightcolor=GREEN)

def card(parent,title=None,subtitle=None,expand=False,pady=(0,14)):
    """White card with optional heading. Returns the frame to fill."""
    frame=ttk.Frame(parent,style='Card.TFrame',padding=(20,16));frame.pack(fill='both' if expand else 'x',expand=expand,pady=pady)
    if title:ttk.Label(frame,text=title,style='CardTitle.TLabel').pack(anchor='w')
    if subtitle:ttk.Label(frame,text=subtitle,style='Muted.TLabel',wraplength=760,justify='left').pack(anchor='w',pady=(2,0))
    if title or subtitle:ttk.Frame(frame,height=12).pack(fill='x')
    return frame

def scroll_page(outer):
    """Page that scrolls with the mouse wheel when its cards do not fit. Returns (canvas, inner frame)."""
    canvas=tk.Canvas(outer,highlightthickness=0,background=PAGE)
    scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview);scroll.pack(side='right',fill='y')
    canvas.pack(side='left',fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
    inner=ttk.Frame(canvas,style='Page.TFrame');item=canvas.create_window(0,0,window=inner,anchor='nw')
    inner.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width-12))
    canvas.bind('<Enter>',lambda _:canvas.bind_all('<MouseWheel>',lambda e:canvas.yview_scroll(int(-e.delta/120),'units')))
    canvas.bind('<Leave>',lambda _:canvas.unbind_all('<MouseWheel>'))
    return canvas,inner

def page_header(parent,title,subtitle=None):
    ttk.Label(parent,text=title,style='PageTitle.TLabel').pack(anchor='w')
    if subtitle:ttk.Label(parent,text=subtitle,style='PageMuted.TLabel',wraplength=800,justify='left').pack(anchor='w',pady=(2,0))
    ttk.Frame(parent,height=16,style='Page.TFrame').pack(fill='x')

def search_field(parent,variable,fonts,style='TFrame',hint='Zoeken'):
    """Entry with a magnifier glyph and a short label, so an empty field still says what it is for."""
    row=ttk.Frame(parent,style=style)
    if fonts.get('icons'):ttk.Label(row,text='',font=(fonts['icons'],11),style='Muted.TLabel' if style=='TFrame' else 'PageMuted.TLabel').pack(side='left',padx=(0,8))
    entry=ttk.Entry(row,textvariable=variable);entry.pack(side='left',fill='x',expand=True)
    if hint:ttk.Label(row,text=hint,style='Muted.TLabel' if style=='TFrame' else 'PageMuted.TLabel').pack(side='left',padx=(8,0))
    return row,entry

def keycaps(parent,label,style='Card'):
    """Shortcut like 'Ctrl+Windows' drawn as separate key chips."""
    row=ttk.Frame(parent,style='TFrame' if style=='Card' else 'Page.TFrame')
    for index,part in enumerate(label.split('+')):
        if index:ttk.Label(row,text='+',style=('Muted.TLabel' if style=='Card' else 'PageMuted.TLabel')).pack(side='left',padx=6)
        ttk.Label(row,text=part.strip(),style='Key.TLabel').pack(side='left')
    return row

def apply_style(root):
    families=set(tkfont.families(root))
    ui=next((f for f in ('Segoe UI Variable Text','Segoe UI') if f in families),'TkDefaultFont')
    display=next((f for f in ('Segoe UI Variable Display','Segoe UI Semibold','Segoe UI') if f in families),ui)
    icons=next((f for f in ('Segoe Fluent Icons','Segoe MDL2 Assets') if f in families),None)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',background=CARD,foreground=NAVY,font=(ui,10),bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,
                    troughcolor=PAGE,focuscolor=GREEN,selectbackground=GREEN_SOFT,selectforeground=NAVY,fieldbackground=CARD)
    style.configure('TFrame',background=CARD)
    style.configure('Page.TFrame',background=PAGE)
    style.configure('Card.TFrame',background=CARD,borderwidth=1,relief='solid',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.configure('Side.TFrame',background=CARD)
    style.configure('TLabel',background=CARD,foreground=NAVY,font=(ui,10))
    style.configure('Muted.TLabel',background=CARD,foreground=MUTED,font=(ui,10))
    style.configure('CardTitle.TLabel',background=CARD,foreground=NAVY,font=(display,13,'bold'))
    style.configure('Big.TLabel',background=CARD,foreground=NAVY,font=(display,16,'bold'))
    style.configure('PageTitle.TLabel',background=PAGE,foreground=NAVY,font=(display,22,'bold'))
    style.configure('PageMuted.TLabel',background=PAGE,foreground=MUTED,font=(ui,10))
    style.configure('Page.TLabel',background=PAGE,foreground=NAVY,font=(ui,10))
    style.configure('Status.TLabel',background=CARD,foreground=MUTED,font=(ui,9))
    style.configure('Key.TLabel',background=PAGE,foreground=NAVY,font=(display,12,'bold'),padding=(12,5),borderwidth=1,relief='solid',bordercolor=LINE)
    style.configure('TCheckbutton',background=CARD,foreground=NAVY,font=(ui,10),indicatorbackground=CARD,indicatorforeground=GREEN,upperbordercolor=LINE,lowerbordercolor=LINE)
    style.map('TCheckbutton',background=[('active',CARD)],indicatorbackground=[('selected',CARD)])
    # Buttons: green primary, white secondary, borderless link.
    style.configure('TButton',background=PAGE,foreground=NAVY,font=(ui,10),padding=(14,7),borderwidth=1,relief='solid',bordercolor=LINE,lightcolor=PAGE,darkcolor=PAGE,focusthickness=0)
    style.map('TButton',background=[('disabled',PAGE),('pressed',GREEN_SOFT),('active',GREEN_SOFT)],foreground=[('disabled','#A3B0AA')],
              bordercolor=[('active',GREEN)],lightcolor=[('pressed',GREEN_SOFT),('active',GREEN_SOFT)],darkcolor=[('pressed',GREEN_SOFT),('active',GREEN_SOFT)])
    style.configure('Primary.TButton',relief='solid',background=GREEN,foreground='#FFFFFF',bordercolor=GREEN,lightcolor=GREEN,darkcolor=GREEN,font=(ui,10,'bold'))
    style.map('Primary.TButton',background=[('disabled',LINE),('pressed',GREEN_DARK),('active',GREEN_DARK)],foreground=[('disabled','#FFFFFF')],
              bordercolor=[('active',GREEN_DARK)],lightcolor=[('active',GREEN_DARK)],darkcolor=[('active',GREEN_DARK)])
    style.configure('Link.TButton',relief='flat',background=CARD,foreground=GREEN_DARK,bordercolor=CARD,lightcolor=CARD,darkcolor=CARD,padding=(0,4),font=(ui,10,'bold'))
    style.map('Link.TButton',background=[('active',CARD),('pressed',CARD)],foreground=[('active',NAVY),('disabled','#A3B0AA')],bordercolor=[('active',CARD)],lightcolor=[('active',CARD)],darkcolor=[('active',CARD)])
    style.configure('TEntry',fieldbackground=CARD,bordercolor=LINE,lightcolor=CARD,darkcolor=CARD,padding=(8,6))
    style.map('TEntry',bordercolor=[('focus',GREEN)],lightcolor=[('focus',GREEN)])
    style.configure('TCombobox',fieldbackground=CARD,background=CARD,bordercolor=LINE,lightcolor=CARD,darkcolor=CARD,arrowcolor=NAVY,padding=(8,5))
    style.map('TCombobox',fieldbackground=[('readonly',CARD)],selectbackground=[('readonly',CARD)],selectforeground=[('readonly',NAVY)],bordercolor=[('focus',GREEN),('hover',GREEN)])
    root.option_add('*TCombobox*Listbox.font',(ui,10));root.option_add('*TCombobox*Listbox.selectBackground',GREEN_SOFT);root.option_add('*TCombobox*Listbox.selectForeground',NAVY)
    style.configure('Treeview',background=CARD,fieldbackground=CARD,foreground=NAVY,rowheight=32,font=(ui,10),borderwidth=0,bordercolor=CARD,lightcolor=CARD,darkcolor=CARD)
    style.map('Treeview',background=[('selected',GREEN_SOFT)],foreground=[('selected',NAVY)])
    style.configure('Treeview.Heading',background=PAGE,foreground=MUTED,font=(ui,9,'bold'),relief='flat',borderwidth=0,padding=(8,6))
    style.map('Treeview.Heading',background=[('active',PAGE)])
    style.configure('Vertical.TScrollbar',background=PAGE,troughcolor=CARD,bordercolor=CARD,lightcolor=PAGE,darkcolor=PAGE,arrowcolor=MUTED,gripcount=0)
    style.configure('TPanedwindow',background=PAGE)
    # Notebook keeps the pages; the sidebar replaces its tab strip.
    style.layout('Pages.TNotebook.Tab',[]);style.configure('Pages.TNotebook',background=PAGE,borderwidth=0,tabmargins=0,bordercolor=PAGE,lightcolor=PAGE,darkcolor=PAGE)
    return dict(ui=ui,display=display,icons=icons)

class NativeApp:
    def __init__(self,app):
        self.app=app;self.root=tk.Toplevel(app.root);self.root.title('Flow Lab')
        self.model_guide=load_guide();self.guide_window=None
        self.root.geometry('1120x780');self.root.minsize(900,620);self.root.configure(background=PAGE)
        self.root.iconbitmap(str(app.root_path/'assets/brand/flow-lab.ico'))
        self.root.update_idletasks()
        import desktop_windows as w
        hwnd=w.ancestor(self.root.winfo_id(),2)
        w.set_style(hwnd,-20,(w.get_style(hwnd,-20)|0x40000)&~0x80)
        self.root.protocol('WM_DELETE_WINDOW',self.hide)
        self.fonts=apply_style(self.root)
        self.status=tk.StringVar(value='Verbinden met de lokale verwerking...')
        self.build_sidebar()
        content=ttk.Frame(self.root,style='Page.TFrame');content.pack(side='left',fill='both',expand=True)
        footer=ttk.Frame(content,style='Page.TFrame');footer.pack(side='bottom',fill='x',padx=30,pady=(8,14))
        ttk.Label(footer,textvariable=self.status,style='PageMuted.TLabel',wraplength=760,justify='left').pack(side='left')
        self.notebook=ttk.Notebook(content,style='Pages.TNotebook');self.notebook.pack(fill='both',expand=True,padx=30,pady=(26,0))
        self.tabs={}
        for key,label in [('home','Dicteren'),('history','Geschiedenis'),('dictionary','Woordenboek'),('snippets','Snippets'),('settings','Instellingen'),('openrouter','OpenRouter'),('learning','Geleerd')]:
            tab=ttk.Frame(self.notebook,style='Page.TFrame');self.tabs[key]=tab;self.notebook.add(tab,text=label)
        self.build_home();self.build_history();self.build_settings();self.build_openrouter()
        page_header(self.tabs['dictionary'],'Woordenboek','Namen en vaktermen die Flow Lab altijd zo moet schrijven.')
        page_header(self.tabs['snippets'],'Snippets','Zeg een sneltoets en Flow Lab plaatst de vaste tekst.')
        self.editors={kind:LibraryEditor(self,kind,self.tabs['snippets' if kind=='snippet' else 'dictionary']) for kind in ('dictionary','snippet')}
        self.build_learning()
        self.notebook.bind('<<NotebookTabChanged>>',lambda _:(self.paint_nav(),self.refresh_selected()))
        self.show('home')

    def build_sidebar(self):
        side=tk.Frame(self.root,background=CARD,width=232,highlightthickness=0);side.pack(side='left',fill='y');side.pack_propagate(False)
        tk.Frame(self.root,background=LINE,width=1).pack(side='left',fill='y')
        with Image.open(self.app.root_path/'assets/brand/flow-lab-logo.png') as logo:
            logo.thumbnail((184,52),Image.Resampling.LANCZOS)
            self.brand_logo=ImageTk.PhotoImage(logo,master=self.root)
        tk.Label(side,image=self.brand_logo,background=CARD).pack(anchor='w',padx=22,pady=(24,26))
        self.nav_items={}
        for item in NAV:
            if item is None:tk.Frame(side,background=LINE,height=1).pack(fill='x',padx=22,pady=12);continue
            key,label,glyph=item
            row=tk.Frame(side,background=CARD,cursor='hand2');row.pack(fill='x',padx=12,pady=1)
            bar=tk.Frame(row,background=CARD,width=3);bar.pack(side='left',fill='y')
            icon=tk.Label(row,text=glyph if self.fonts['icons'] else '',font=(self.fonts['icons'] or self.fonts['ui'],13),background=CARD,foreground=MUTED,width=2)
            icon.pack(side='left',padx=(10,6),pady=9)
            name=tk.Label(row,text=label,font=(self.fonts['ui'],10),background=CARD,foreground=NAVY,anchor='w');name.pack(side='left',fill='x',expand=True)
            for widget in (row,icon,name):
                widget.bind('<Button-1>',lambda _,k=key:self.show(k))
                widget.bind('<Enter>',lambda _,k=key:self.paint_nav(hover=k));widget.bind('<Leave>',lambda _:self.paint_nav())
            self.nav_items[key]=(row,bar,icon,name)
        bottom=tk.Frame(side,background=CARD);bottom.pack(side='bottom',fill='x',padx=22,pady=18)
        self.status_dot=tk.Label(bottom,text='●',font=(self.fonts['ui'],10),background=CARD,foreground=MUTED)
        self.status_dot.grid(row=0,column=0,sticky='nw',padx=(0,6))
        self.service_text=tk.StringVar(value='Verbinden...')
        tk.Label(bottom,textvariable=self.service_text,font=(self.fonts['ui'],9),background=CARD,foreground=NAVY,justify='left',wraplength=160,anchor='w').grid(row=0,column=1,sticky='w')
        tk.Label(bottom,text='Het kruisje verbergt dit venster.\nDicteren blijft dan actief.',font=(self.fonts['ui'],8),background=CARD,foreground=MUTED,justify='left').grid(row=1,column=0,columnspan=2,sticky='w',pady=(12,8))
        ttk.Button(bottom,text='Flow Lab afsluiten',command=self.app.quit_all).grid(row=2,column=0,columnspan=2,sticky='we')
        bottom.columnconfigure(1,weight=1)

    def paint_nav(self,hover=None):
        if not hasattr(self,'tabs'):return
        selected=self.notebook.select()
        for key,(row,bar,icon,name) in self.nav_items.items():
            on=str(self.tabs[key])==selected;bg=GREEN_SOFT if on else (PAGE if key==hover else CARD)
            for widget in (row,icon,name):widget.configure(background=bg)
            bar.configure(background=GREEN if on else bg);icon.configure(foreground=GREEN_DARK if on else MUTED)
            name.configure(font=(self.fonts['ui'],10,'bold' if on else 'normal'))

    def set_service(self,text,ok=True):
        self.service_text.set(text);self.status_dot.configure(foreground=GREEN if ok else ORANGE)

    def exists(self):return bool(self.root.winfo_exists())

    def request(self,path,callback,method='GET',data=None):
        def task():
            try:
                response=httpx.request(method,self.app.service_url+path,json=data,
                    headers={'Origin':self.app.service_url},timeout=90 if path.startswith('/api/openrouter/') else 8,trust_env=False)
                if response.is_error:
                    try:detail=response.json().get('detail','Actie mislukt')
                    except Exception:detail='Lokale verwerking antwoordt niet goed'
                    raise ValueError(str(detail))
                result=response.json();error=None
            except Exception as exc:result=None;error=str(exc)
            self.app.events.put(('ui_result',self,callback,result,error))
        threading.Thread(target=task,daemon=True).start()

    def deliver(self,callback,result,error):
        if not self.exists():return
        if error:self.status.set('Niet gelukt: '+error[:170])
        callback(result,error)
        self.app.write_state()

    def show(self,panel='home'):
        if panel not in self.tabs:panel='home'
        self.notebook.select(self.tabs[panel]);self.paint_nav();self.status.set('');self.root.deiconify();self.root.lift()
        self.refresh_selected();self.app.write_state()

    def hide(self):
        self.root.withdraw();self.app.write_state()

    def refresh_selected(self):
        selected=self.notebook.select()
        if selected==str(self.tabs['history']):self.load_history()
        elif selected==str(self.tabs['dictionary']):self.editors['dictionary'].load()
        elif selected==str(self.tabs['snippets']):self.editors['snippet'].load()
        elif selected==str(self.tabs['settings']):self.refresh_settings()
        elif selected==str(self.tabs['openrouter']):self.load_openrouter_status()
        elif selected==str(self.tabs['learning']):self.refresh_learning()
        else:self.refresh_home()

    def build_settings(self):
        self.settings_canvas,tab=scroll_page(self.tabs['settings'])
        page_header(tab,'Instellingen','Sneltoets, verwerking en leren. Wijzigingen gelden vanaf je volgende dictaat.')
        shortcuts=card(tab,'Sneltoets','Sneltoetsen zijn gepauzeerd zolang deze pagina openstaat. Ga daarna terug naar Dicteren.')
        self.settings_status=tk.StringVar();ttk.Label(shortcuts,textvariable=self.settings_status,style='TLabel').pack(anchor='w')
        row=ttk.Frame(shortcuts);row.pack(fill='x',pady=12)
        _,mask,vk,_=shortcut(self.app.config['hotkey'])
        self.modifier_vars={k:tk.BooleanVar(value=bool(mask&flag)) for k,flag in MODIFIERS.items()}
        for k in MODIFIERS:ttk.Checkbutton(row,text=LABELS[k],variable=self.modifier_vars[k]).pack(side='left',padx=(0,16))
        self.key_choices={'Geen extra toets':None,**{label:key for key,(_,label) in KEYS.items()}}
        self.extra_key=tk.StringVar(value=next((label for label,key in self.key_choices.items() if key and KEYS[key][0]==vk),'Geen extra toets'))
        ttk.Combobox(row,textvariable=self.extra_key,values=list(self.key_choices),state='readonly',width=20).pack(side='left')
        buttons=ttk.Frame(shortcuts);buttons.pack(fill='x')
        def preset():
            for key,var in self.modifier_vars.items():var.set(key in ('ctrl','win'))
            self.extra_key.set('Geen extra toets');self.settings_status.set('Ctrl+Windows gekozen. Klik op Sneltoets opslaan.')
        def save_key():
            parts=[k for k,var in self.modifier_vars.items() if var.get()]
            extra=self.key_choices[self.extra_key.get()]
            if extra:parts.append(extra)
            try:value=shortcut('-'.join(parts))[0]
            except ValueError as exc:self.settings_status.set(str(exc));return
            self.app.events.put(('key',value))
        ttk.Button(buttons,text='Sneltoets opslaan',style='Primary.TButton',command=save_key).pack(side='left')
        ttk.Button(buttons,text='Ctrl+Windows kiezen',command=preset).pack(side='left',padx=8)
        self.settings_replay=tk.StringVar();ttk.Label(shortcuts,textvariable=self.settings_replay,style='Muted.TLabel').pack(anchor='w',pady=(12,0))
        ttk.Label(shortcuts,text='Houd ingedrukt om te spreken, dubbel indrukken zet de opname vast. Sluit Wispr als je dezelfde combinatie gebruikt.',style='Muted.TLabel',wraplength=760,justify='left').pack(anchor='w',pady=(2,0))
        options=card(tab,'Tekstverwerking','Hoe Flow Lab je spraak omzet en opmaakt.')
        self.preference_vars={};self.preference_choices={
            'formatter':{'Volledig lokaal':'local','Lokaal zonder AI-opmaak':'verbatim','Lokale audio, cloudopmaak':'cloud-mini','Lokale audio, OpenRouter gratis':'openrouter-free'},
            'paragraphs':{'Natuurlijk':'normaal','Meer witregels':'ruim','Alleen modelopmaak':'compact'},
            'style':{'Natuurlijk bericht':'bericht','Notitie of opsomming':'notitie','Woorden behouden':'letterlijk'}}
        grid=ttk.Frame(options);grid.pack(fill='x')
        for index,(key,label) in enumerate([('formatter','Verwerking'),('paragraphs',"Alinea's"),('style','Schrijfstijl')]):
            ttk.Label(grid,text=label).grid(row=index,column=0,sticky='w',padx=(0,20),pady=5)
            mapping=self.preference_choices[key];value=self.app.config.get(key,{'style':'bericht','paragraphs':'normaal','formatter':'local'}[key])
            var=tk.StringVar(value=next((name for name,item in mapping.items() if item==value),next(iter(mapping))))
            self.preference_vars[key]=var
            ttk.Combobox(grid,textvariable=var,values=list(mapping),state='readonly',width=33).grid(row=index,column=1,sticky='w',pady=5)
        def save_preferences():
            data={key:self.preference_choices[key][var.get()] for key,var in self.preference_vars.items()}
            self.app.events.put(('preferences',data))
        self.settings_model_hint=tk.StringVar()
        ttk.Label(grid,textvariable=self.settings_model_hint,style='Muted.TLabel',wraplength=300,justify='left').grid(row=0,column=2,rowspan=3,sticky='nw',padx=(28,0),pady=5)
        actions=ttk.Frame(options);actions.pack(fill='x',pady=(12,0))
        ttk.Button(actions,text='Verwerking opslaan',style='Primary.TButton',command=save_preferences).pack(side='left')
        ttk.Button(actions,text='Welke verwerking past bij mij?',command=self.show_model_guide).pack(side='left',padx=8)
        ttk.Button(actions,text='OpenRouter instellen',style='Link.TButton',command=lambda:self.show('openrouter')).pack(side='left',padx=8)
        learn=card(tab,'Leren van correcties','Verbeter binnen een minuut in hetzelfde tekstvak. Na 1,5 seconde rust beoordeelt Flow Lab een duidelijke correctie.')
        self.learning_enabled=tk.BooleanVar(value=self.app.config.get('auto_learn',False))
        ttk.Checkbutton(learn,text='Automatisch leren van mijn woordcorrecties',variable=self.learning_enabled,
                        command=lambda:self.app.events.put(('learning_toggle',self.learning_enabled.get()))).pack(anchor='w')
        ttk.Button(learn,text='Recent geleerde correcties bekijken',style='Link.TButton',command=lambda:self.show('learning')).pack(anchor='w',pady=(8,0))
        def explain_settings(*_):
            selected=self.preference_choices['formatter'].get(self.preference_vars['formatter'].get(),'local')
            self.settings_model_hint.set(self.model_guide['desktop'][selected])
        self.preference_vars['formatter'].trace_add('write',explain_settings);explain_settings()
        privacy=card(tab,'Privacy')
        for line in ('Volledig lokaal houdt audio en tekst op deze pc.','Audio blijft 24 uur versleuteld bewaard, zodat je een opname opnieuw kunt verwerken.','Bij cloudopmaak gaat alleen de herkende tekst naar de gekozen provider.'):
            ttk.Label(privacy,text='✓  '+line,wraplength=760,justify='left').pack(anchor='w',pady=2)

    def refresh_settings(self):
        self.learning_enabled.set(self.app.config.get('auto_learn',False))
        self.settings_status.set('Actieve dicteersneltoets: '+shortcut_label(self.app.config['hotkey']))
        for key,var in self.preference_vars.items():
            value=self.app.config.get(key,{'style':'bericht','paragraphs':'normaal','formatter':'local'}[key])
            var.set(next((name for name,item in self.preference_choices[key].items() if item==value),next(iter(self.preference_choices[key]))))
        import desktop_windows as w
        replay=w.REPLAY_KEYS.get(self.app.replay_key,(None,None,'Niet beschikbaar'))[2]
        self.settings_replay.set('Laatste resultaat opnieuw plaatsen: '+replay)

    def build_learning(self):
        tab=self.tabs['learning']
        page_header(tab,'Geleerd','Duidelijke correcties naar bekende namen worden onthouden. Nieuwe woorden vragen herhaling; twijfelgevallen blijven een voorstel.')
        self.learning_status=tk.StringVar(value='Correcties worden lokaal beoordeeld. Volledige tekstvelden worden niet opgeslagen.')
        ttk.Label(tab,textvariable=self.learning_status,style='PageMuted.TLabel',wraplength=800).pack(anchor='w',pady=(0,10))
        box=card(tab,expand=True)
        self.learning_rows={}
        self.learning_tree=ttk.Treeview(box,columns=('wrong','right','state','count'),show='headings',selectmode='browse')
        for key,label,width in [('wrong','Gehoorde schrijfwijze',235),('right','Jouw correctie',235),('state','Status',160),('count','Dictaten',70)]:
            self.learning_tree.heading(key,text=label,anchor='w');self.learning_tree.column(key,width=width)
        self.learning_tree.pack(fill='both',expand=True)
        self.learning_tree.bind('<<TreeviewSelect>>',lambda _:self.learning_selection())
        self.learning_detail=tk.StringVar();ttk.Label(box,textvariable=self.learning_detail,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=10)
        buttons=ttk.Frame(box);buttons.pack(fill='x')
        self.learning_buttons={}
        for action,label in [('accept','Onthouden'),('ignore','Negeren'),('undo','Ongedaan maken')]:
            button=ttk.Button(buttons,text=label,style='Primary.TButton' if action=='accept' else 'TButton',command=lambda a=action:self.review_learning(a),state='disabled')
            button.pack(side='left',padx=(0,8));self.learning_buttons[action]=button
        ttk.Button(buttons,text='Vernieuwen',style='Link.TButton',command=self.load_learning).pack(side='right')

    def refresh_learning(self):
        self.learning_enabled.set(self.app.config.get('auto_learn',False));self.load_learning()

    def load_learning(self):
        def loaded(data,error):
            if error:self.learning_detail.set(error);return
            selection=self.learning_tree.selection()
            self.learning_rows={row['id']:row for row in data['items']}
            self.learning_tree.delete(*self.learning_tree.get_children())
            labels={'pending':'Voorstel','learned':'Onthouden','ignored':'Genegeerd','undone':'Ongedaan','withdrawn':'Teruggenomen','conflict':'Controle nodig','covered':'Staat al in woordenboek'}
            for row in data['items']:
                self.learning_tree.insert('','end',iid=row['id'],values=(row['wrong'],row['right'],labels.get(row['state'],row['state']),row['observations']))
            if selection and selection[0] in self.learning_rows:self.learning_tree.selection_set(selection[0])
            self.learning_selection()
        self.request('/api/learning',loaded)

    def learning_selection(self):
        selected=self.learning_tree.selection();row=self.learning_rows.get(selected[0]) if selected else None
        for action,button in self.learning_buttons.items():
            allowed=bool(row) and ((action=='undo' and row['state']=='learned') or (action=='accept' and row['state'] in ('pending','ignored','undone','withdrawn')) or action=='ignore' and row['state'] in ('pending','learned'))
            button.configure(state='normal' if allowed else 'disabled')
        self.learning_detail.set(row['reason'] if row else 'Selecteer een schrijfwijze om deze te beheren.')

    def review_learning(self,action):
        selected=self.learning_tree.selection()
        if not selected:return
        for button in self.learning_buttons.values():button.configure(state='disabled')
        def reviewed(data,error):
            self.learning_detail.set(error if error else 'Bijgewerkt. De schrijfwijze geldt vanaf je volgende dictaat.')
            self.load_learning()
        self.request('/api/learning/'+quote(selected[0],safe='')+'/'+action,reviewed,'POST',{})

    def build_home(self):
        tab=self.tabs['home']
        page_header(tab,'Dicteren','Klik in een tekstvak in welke app dan ook, en spreek.')
        hero=card(tab)
        top=ttk.Frame(hero);top.pack(fill='x')
        ttk.Label(top,text='Houd ingedrukt',style='Muted.TLabel').pack(side='left',padx=(0,12))
        self.hotkey_row=ttk.Frame(top);self.hotkey_row.pack(side='left')
        self.shortcut_text=tk.StringVar()  # Kept for the status file and tests; the chips show it visually.
        tips=ttk.Frame(hero);tips.pack(fill='x',pady=(16,0))
        for column,(head,body) in enumerate([('Laat los','Flow Lab verwerkt en plaatst je tekst in het tekstvak.'),('Twee keer snel','Zet de opname vast. Nog een keer drukken stopt.'),('Tot 5 minuten','Lange dictaten worden in delen verwerkt.')]):
            cell=ttk.Frame(tips);cell.grid(row=0,column=column,sticky='nw',padx=(0,24));tips.columnconfigure(column,weight=1,uniform='tips')
            ttk.Label(cell,text=head,font=(self.fonts['ui'],10,'bold')).pack(anchor='w')
            ttk.Label(cell,text=body,style='Muted.TLabel',wraplength=230,justify='left').pack(anchor='w')
        replay=ttk.Frame(hero);replay.pack(fill='x',pady=(16,0))
        self.replay_row=ttk.Frame(replay);self.replay_row.pack(side='left')
        self.replay_text=tk.StringVar()
        ttk.Label(replay,text='plaatst je laatste tekst opnieuw',style='Muted.TLabel').pack(side='left',padx=12)
        latest=card(tab,expand=True)
        head=ttk.Frame(latest);head.pack(fill='x')
        ttk.Label(head,text='Laatste tekst',style='CardTitle.TLabel').pack(side='left')
        ttk.Button(head,text='Kopiëren',style='Primary.TButton',command=lambda:self.copy(self.latest.get('1.0','end-1c'))).pack(side='right')
        self.insertion_message=tk.StringVar(value=getattr(self.app,'last_insertion_message',''))
        ttk.Label(latest,textvariable=self.insertion_message,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(4,10))
        self.latest=text_box(latest,6);self.latest.pack(fill='both',expand=True)
        mode=card(tab)
        row=ttk.Frame(mode);row.pack(fill='x')
        ttk.Label(row,text='Verwerking',style='CardTitle.TLabel').pack(side='left',padx=(0,16))
        self.mode_choices={'Volledig lokaal':'local','Lokaal zonder AI-opmaak':'verbatim','Lokale audio, cloudopmaak':'cloud-mini','Lokale audio, OpenRouter gratis':'openrouter-free'}
        self.mode=tk.StringVar(value=next(name for name,value in self.mode_choices.items() if value==self.app.config['formatter']))
        choice=ttk.Combobox(row,textvariable=self.mode,values=list(self.mode_choices),state='readonly',width=31)
        choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda _:self.app.events.put(('mode',self.mode_choices[self.mode.get()])))
        ttk.Button(row,text='Welke modellen kies ik?',style='Link.TButton',command=self.show_model_guide).pack(side='left',padx=14)
        self.home_model_hint=tk.StringVar()
        def explain_home(*_):self.home_model_hint.set(self.model_guide['desktop'][self.mode_choices[self.mode.get()]])
        self.mode.trace_add('write',explain_home);explain_home()
        ttk.Label(mode,textvariable=self.home_model_hint,style='Muted.TLabel',wraplength=760,justify='left').pack(anchor='w',pady=(8,0))
        # Recovery only takes space when there is something to recover.
        self.recovery_card=ttk.Frame(tab,style='Card.TFrame',padding=(20,16))
        ttk.Label(self.recovery_card,text='Opnames van de afgelopen 24 uur',style='CardTitle.TLabel').pack(anchor='w')
        self.recovery_hint=tk.StringVar(value='Geen opname klaar voor herstel.')
        ttk.Label(self.recovery_card,textvariable=self.recovery_hint,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(2,10))
        actions=ttk.Frame(self.recovery_card);actions.pack(fill='x')
        self.recovery_choice=tk.StringVar();self.recovery_choices={}
        self.recovery_combo=ttk.Combobox(actions,textvariable=self.recovery_choice,state='readonly',width=47)
        self.recovery_combo.pack(side='left',fill='x',expand=True)
        self.retry_button=ttk.Button(actions,text='Opnieuw verwerken',style='Primary.TButton',command=self.retry_selected)
        self.retry_button.pack(side='left',padx=8)
        self.discard_button=ttk.Button(actions,text='Opname verwijderen',command=self.discard_selected)
        self.discard_button.pack(side='left')
        self.retry_basic_button=ttk.Button(self.recovery_card,text='Herstellen zonder AI-opmaak (lokaal)',style='Link.TButton',command=lambda:self.retry_selected(True))
        self.retry_basic_button.pack(anchor='w',pady=(8,0))

    def show_model_guide(self):
        if self.guide_window and self.guide_window.winfo_exists():self.guide_window.lift();return
        dialog=tk.Toplevel(self.root);self.guide_window=dialog;dialog.configure(background=PAGE)
        dialog.title('Flow Lab - Welke modellen kies ik?');dialog.geometry('790x650');dialog.minsize(620,450);dialog.transient(self.root)
        frame=ttk.Frame(dialog,style='Page.TFrame',padding=18);frame.pack(fill='both',expand=True)
        text=text_box(frame,10);text.configure(padx=16,pady=14)
        scroll=ttk.Scrollbar(frame,command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0',guide_text(self.model_guide));text.configure(state='disabled')
        ttk.Button(dialog,text='Sluiten',style='Primary.TButton',command=dialog.destroy).pack(pady=(0,14))

    def refresh_home(self):
        store=getattr(self.app,'recovery_store',None)
        entries=store.entries() if store else []
        self.recovery_choices={f"{datetime.fromtimestamp(item['created_at']).strftime('%d-%m %H:%M:%S')} | {item['duration_s']:.0f} s | {item.get('config',{}).get('formatter','onleesbaar')}"+(" | gedeeltelijk" if item.get('partial') else ''):item['id'] for item in entries}
        self.recovery_combo.configure(values=list(self.recovery_choices))
        if self.recovery_choice.get() not in self.recovery_choices:self.recovery_choice.set(next(iter(self.recovery_choices),''))
        enabled=bool(entries) and getattr(self.app,'state','idle')=='idle'
        self.retry_button.configure(state='normal' if enabled else 'disabled');self.discard_button.configure(state='normal' if enabled else 'disabled')
        self.retry_basic_button.configure(state='normal' if enabled else 'disabled')
        self.recovery_hint.set('Audio blijft 24 uur versleuteld bewaard, ook na succes. Maximaal 500 MB. Opnieuw verwerken gebruikt de oorspronkelijke modelkeuze.' if entries else 'Nog geen bewaarde opname. Nieuwe desktopopnames blijven hier 24 uur beschikbaar, ook na herstart.')
        if any(not item.get('persistent',True) for item in entries):self.recovery_hint.set('Let op: herstelkopie alleen in geheugen. Sluit Flow Lab niet voordat je deze hebt hersteld.')
        if entries:self.recovery_card.pack(fill='x',pady=(0,14))
        else:self.recovery_card.pack_forget()
        self.insertion_message.set(getattr(self.app,'last_insertion_message',''))
        label=shortcut_label(self.app.config['hotkey'])
        if label!=self.shortcut_text.get():
            self.shortcut_text.set(label)
            for child in self.hotkey_row.winfo_children():child.destroy()
            keycaps(self.hotkey_row,label).pack(side='left')
        import desktop_windows as w
        key=w.REPLAY_KEYS.get(self.app.replay_key,(None,None,'Geen vrije sneltoets'))[2]
        if key!=self.replay_text.get():
            self.replay_text.set(key)
            for child in self.replay_row.winfo_children():child.destroy()
            keycaps(self.replay_row,key).pack(side='left')
        self.mode.set(next(name for name,value in self.mode_choices.items() if value==self.app.config['formatter']))
        def status(data,error):
            if error:self.set_service('Lokale verwerking niet bereikbaar',False);return
            self.set_service('Bezig met verwerken' if data['busy'] else 'Klaar om te dicteren')
            self.status.set('Lokale verwerking actief. '+('Er wordt momenteel verwerkt.' if data['busy'] else 'Klaar om te dicteren.'))
        self.request('/api/status',status)
        def latest(data,error):
            if not error:
                set_text(self.latest,data['items'][0]['text'] if data['items'] else '')
                self.latest.configure(state='disabled')
        self.request('/api/history?limit=1',latest)

    def retry_selected(self,without_ai=False):
        key=self.recovery_choices.get(self.recovery_choice.get())
        if key:
            self.retry_button.configure(state='disabled');self.discard_button.configure(state='disabled')
            self.retry_basic_button.configure(state='disabled')
            self.app.events.put(('retry_recording',key,True) if without_ai else ('retry_recording',key))

    def discard_selected(self):
        key=self.recovery_choices.get(self.recovery_choice.get())
        if key and messagebox.askyesno('Herstelopname verwijderen','Deze opname definitief verwijderen?',parent=self.root):
            self.app.events.put(('discard_recording',key))

    def copy(self,text):
        if not text:return
        import desktop_windows as w
        try:w.copy_text(self.app.hwnd,text);self.status.set('Tekst gekopieerd.')
        except Exception:self.status.set('Klembord is bezet. Probeer opnieuw.')

    def build_openrouter(self):
        _,tab=scroll_page(self.tabs['openrouter']);self.router_models=[];self.router_saved_model=''
        self.router_key_checked=False;self.router_key_locked=False;self.router_key_editing=False;self.router_key_usable=False
        self.router_testing=False;self.router_fetching=False
        page_header(tab,'OpenRouter','Kies hier je gratis opmaakmodel. Audio blijft lokaal; alleen de herkende tekst gaat naar de gekozen provider.')
        self.router_status=tk.StringVar(value='Sleutelstatus ophalen...')
        ttk.Label(tab,textvariable=self.router_status,style='PageMuted.TLabel',wraplength=800).pack(anchor='w',pady=(0,12))
        keycard=card(tab,'Sleutel','Er is één actieve sleutel. De opgeslagen waarde wordt nooit getoond.')
        self.router_key_notice=tk.StringVar(value='Sleutelstatus wordt gecontroleerd.')
        ttk.Label(keycard,textvariable=self.router_key_notice,style='Muted.TLabel').pack(anchor='w',pady=(0,8))
        row=ttk.Frame(keycard);row.pack(fill='x');self.router_key=tk.StringVar()
        self.router_key_input=ttk.Entry(row,textvariable=self.router_key,show='*',width=40,state='disabled')
        self.router_key_input.pack(side='left',fill='x',expand=True)
        self.router_key_save=ttk.Button(row,text='Sleutel veilig opslaan',style='Primary.TButton',command=self.save_router_key,state='disabled')
        self.router_key_save.pack(side='left',padx=(8,0))
        self.router_key_change=ttk.Button(row,text='Sleutel wijzigen',command=self.edit_router_key,state='disabled')
        self.router_key_change.pack(side='left',padx=(8,0))
        self.router_key_cancel=ttk.Button(keycard,text='Wijzigen annuleren',style='Link.TButton',command=self.cancel_router_key)
        self.router_key.trace_add('write',lambda *_:self.refresh_router_controls())
        modelcard=card(tab,'Model kiezen','Begin met de kleine keuzelijst. De voorstellen zijn startpunten voor een proef, geen bewezen snelheidsranglijst.')
        self.router_recommendation=tk.StringVar(value='Haal de modellen op voor een concreet eerste voorstel.')
        ttk.Label(modelcard,textvariable=self.router_recommendation,style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(0,8))
        self.router_model=tk.StringVar();self.router_choice=tk.StringVar();self.router_choice_map={}
        self.router_combo=ttk.Combobox(modelcard,textvariable=self.router_choice,state='readonly',width=70);self.router_combo.pack(fill='x')
        self.router_combo.bind('<<ComboboxSelected>>',self.router_choice_selected)
        self.router_model_hint=tk.StringVar(value='Haal de actuele modellen op om de eerste voorstellen te zien.')
        ttk.Label(modelcard,textvariable=self.router_model_hint,style='Muted.TLabel',wraplength=800,justify='left').pack(anchor='w',pady=(8,0))
        self.router_all=tk.BooleanVar(value=False)
        ttk.Checkbutton(modelcard,text='Alle gratis modellen tonen (meer keuzes)',variable=self.router_all,command=self.populate_router_choices).pack(anchor='w',pady=(8,0))
        buttons=ttk.Frame(modelcard);buttons.pack(fill='x',pady=(10,0))
        self.router_fetch_button=ttk.Button(buttons,text='Modellen ophalen',command=self.fetch_router_models);self.router_fetch_button.pack(side='left',padx=(0,8))
        self.router_model_save=ttk.Button(buttons,text='Modelkeuze opslaan',style='Primary.TButton',command=self.save_router_model,state='disabled');self.router_model_save.pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='Sleutel / quotum controleren',command=self.check_router_key).pack(side='left')
        self.router_saved_notice=tk.StringVar(value='Nog geen model opgeslagen.')
        ttk.Label(modelcard,textvariable=self.router_saved_notice,style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(10,0))
        self.router_activate=ttk.Button(modelcard,text='OpenRouter gebruiken voor dictatie',command=self.activate_router,state='disabled');self.router_activate.pack(anchor='w',pady=(8,0))
        ttk.Label(modelcard,text='In Instellingen kies je lokaal of cloud. Het precieze OpenRouter-model kies je op deze pagina.',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(8,0))
        privacy=card(tab,'Privacy','Geen geschikte provider gevonden? Probeer een ander model met dezelfde privacykeuze. Je OpenRouter-accountbeleid blijft ook gelden.')
        self.router_private=tk.BooleanVar(value=True);privacy_row=ttk.Frame(privacy);privacy_row.pack(fill='x')
        ttk.Checkbutton(privacy_row,text='Alleen providers zonder gegevensverzameling',variable=self.router_private).pack(side='left')
        def save_privacy():
            def saved(data,error):self.router_status.set(error if error else 'Privacykeuze opgeslagen. Je accountbeleid blijft ook gelden.')
            self.request('/api/openrouter/privacy',saved,'POST',{'data_collection':'deny' if self.router_private.get() else 'allow'})
        ttk.Button(privacy_row,text='Privacykeuze opslaan',command=save_privacy).pack(side='left',padx=10)
        ttk.Label(privacy,text='Als je dit uitzet, kunnen providers tekst bewaren of voor training gebruiken volgens hun voorwaarden.',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(8,0))
        test_card=card(tab,'Proef zonder microfoon','1. Kies een model en sla het op. 2. Test de voorbeeldtekst. 3. Controleer de tijd én of de inhoud klopt.')
        self.router_test_notice=tk.StringVar(value='De proef gebruikt het opgeslagen model. Je hoeft niet te praten.')
        ttk.Label(test_card,textvariable=self.router_test_notice,style='Muted.TLabel',wraplength=800).pack(anchor='w')
        ttk.Label(test_card,text='Voorbeeld: hallo Alex de voorbeeldplanning is klaar ik kan vrijdag niet maar maandag wel het bedrag is 1500 euro exclusief btw',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(8,0))
        self.router_test_button=ttk.Button(test_card,text='Opgeslagen model testen met voorbeeldtekst',command=self.test_router_model,state='disabled');self.router_test_button.pack(anchor='w',pady=(10,0))
        self.router_result=text_box(test_card,4,10);self.router_result.pack(fill='both',expand=True,pady=(10,0));self.router_result.configure(state='disabled')
        ttk.Label(test_card,text='Echt dicteren? Activeer OpenRouter hierboven. Klik daarna in je gewenste tekstvak en gebruik je gewone dicteersneltoets.',style='Muted.TLabel',wraplength=800).pack(anchor='w',pady=(8,0))

    def refresh_router_controls(self):
        if not hasattr(self,'router_test_button') or not self.exists():return
        editing=self.router_key_checked and self.router_key_editing
        self.router_key_input.configure(state='normal' if editing else 'disabled')
        self.router_key_save.configure(state='normal' if editing and bool(self.router_key.get().strip()) else 'disabled',text=('Sleutel vervangen' if editing else 'Sleutel opgeslagen') if self.router_key_locked else 'Sleutel veilig opslaan')
        self.router_key_change.configure(state='normal' if self.router_key_locked and not editing else 'disabled')
        if self.router_key_locked and editing:self.router_key_cancel.pack(anchor='w',pady=(6,0))
        else:self.router_key_cancel.pack_forget()
        chosen=self.router_model.get();saved=self.router_saved_model
        present=chosen in {m['id'] for m in self.router_models}
        ready=self.router_key_usable and not editing and bool(saved) and chosen==saved
        self.router_model_save.configure(state='normal' if present and chosen!=saved and not self.router_fetching else 'disabled')
        self.router_fetch_button.configure(state='disabled' if self.router_fetching else 'normal')
        self.router_test_button.configure(state='normal' if ready and not self.router_testing else 'disabled')
        active=self.app.config.get('formatter')=='openrouter-free'
        self.router_activate.configure(state='normal' if ready and not active else 'disabled',text='OpenRouter is actief voor dictatie' if active else 'OpenRouter gebruiken voor dictatie')
        self.router_saved_notice.set('Opgeslagen model: '+saved if saved else 'Nog geen model opgeslagen. Een keuze in de lijst is pas opgeslagen na de knop.')
        self.router_test_notice.set(('Sla de nieuwe modelkeuze eerst op. ' if chosen!=saved else '')+'De proef gebruikt '+(saved or 'nog geen opgeslagen model')+'. Geen microfoon of echte dictaten.')

    def edit_router_key(self):
        if not self.router_key_locked:return
        self.router_key_editing=True;self.router_key.set('');self.refresh_router_controls();self.router_key_input.focus_set()

    def cancel_router_key(self):
        self.router_key_editing=False;self.router_key.set('');self.refresh_router_controls()

    def save_router_key(self):
        if not self.router_key_checked or not self.router_key_editing:return
        key=self.router_key.get().strip()
        if not key:return
        self.router_key.set('');self.router_key_checked=False;self.refresh_router_controls()
        def saved(data,error):
            if error:
                self.router_key_checked=True;self.refresh_router_controls();self.router_status.set(error);return
            self.load_openrouter_status()
            self.router_status.set('Sleutel opgeslagen. Er is één actieve sleutel.')
        self.request('/api/openrouter/key',saved,'POST',{'key':key})

    def populate_router_choices(self):
        chosen=self.router_model.get();choices=model_choices(self.router_models,self.router_saved_model,self.router_all.get())
        available={m['id'] for m in self.router_models}
        first=next((key for key in SUGGESTIONS if key in available),None)
        self.router_recommendation.set('Beginproef: '+SUGGESTIONS[first][0]+'. Selecteer dit zelf in de lijst; je huidige keuze blijft behouden.' if first else 'Haal de actuele modellen op. Als onze startpunten ontbreken, kun je de overige modellen zelf vergelijken.')
        ids={item['id'] for item in choices}
        if chosen and chosen not in ids:
            current=next((m for m in self.router_models if m['id']==chosen),None)
            choices.append({'id':chosen,'label':('Geselecteerd: '+current.get('name',chosen)) if current else 'Opgeslagen keuze: '+chosen,
                            'hint':'Deze keuze is nog niet opnieuw gecontroleerd. Haal de modellen op en test de opgeslagen keuze.'})
        self.router_choice_map={item['label']:item for item in choices}
        self.router_combo.configure(values=list(self.router_choice_map))
        self.router_choice.set(next((label for label,item in self.router_choice_map.items() if item['id']==chosen),''))
        item=self.router_choice_map.get(self.router_choice.get())
        self.router_model_hint.set(item['hint'] if item else ROUTER_GUIDE_LIMITS)
        self.refresh_router_controls()

    def router_choice_selected(self,event=None):
        item=self.router_choice_map.get(self.router_choice.get())
        if item:self.router_model.set(item['id']);self.router_model_hint.set(item['hint'])
        self.refresh_router_controls()

    def fetch_router_models(self):
        self.router_fetching=True;self.router_status.set('Actuele gratis modellen ophalen...');self.refresh_router_controls()
        def loaded(data,error):
            self.router_fetching=False
            if error:self.router_status.set(error);self.refresh_router_controls();return
            self.router_models=data['models'];self.populate_router_choices()
            self.router_status.set(str(len(self.router_models))+' gratis tekstmodellen gevonden. Eerst zie je enkele startpunten en eventueel je huidige keuze.')
        self.request('/api/openrouter/models?refresh=true',loaded)

    def save_router_model(self):
        chosen=self.router_model.get()
        if chosen not in {m['id'] for m in self.router_models}:return
        def saved(data,error):
            if error:self.router_status.set(error);return
            self.router_saved_model=data['model'];self.populate_router_choices()
            self.router_status.set('Model opgeslagen. Test het hieronder of kies OpenRouter gebruiken voor dictatie.')
        self.request('/api/openrouter/model',saved,'POST',{'model':chosen})

    def activate_router(self):
        if not self.router_key_usable or self.router_key_editing or not self.router_saved_model or self.router_model.get()!=self.router_saved_model:return
        self.app.events.put(('preferences',{'formatter':'openrouter-free','paragraphs':self.app.config.get('paragraphs','normaal'),'style':self.app.config.get('style','bericht')}))
        self.root.after(250,self.refresh_router_controls)

    def check_router_key(self):
        def checked(data,error):
            if error:self.router_status.set(error);return
            remaining=data['free_requests'].get('remaining')
            self.router_status.set('Sleutel geldig. Gratis verzoeken resterend vandaag: '+str(remaining if remaining is not None else 'niet opgegeven')+'.')
        self.request('/api/openrouter/check',checked,'POST')

    def test_router_model(self):
        if not self.router_key_usable or self.router_key_editing or not self.router_saved_model or self.router_model.get()!=self.router_saved_model or self.router_testing:return
        tested_model=self.router_saved_model;self.router_testing=True;self.refresh_router_controls()
        self.router_status.set('Voorbeeldtekst testen met '+tested_model+'...')
        def tested(data,error):
            self.router_testing=False;self.refresh_router_controls()
            if error:
                self.router_status.set(error);set_text(self.router_result,'Proef mislukt voor '+tested_model+'. '+error);self.router_result.configure(state='disabled');return
            set_text(self.router_result,'Model: '+tested_model+'\n\n'+data['text']);self.router_result.configure(state='disabled')
            self.router_status.set(f"Opmaakproef in {data['ms']/1000:.2f} s. "+(data.get('warning') or 'Controleer zelf ook de inhoud. Dit meet geen spraakherkenning of plaatsing.'))
        self.request('/api/openrouter/test',tested,'POST')

    def load_openrouter_status(self):
        def loaded(data,error):
            if error:self.router_status.set(error);return
            self.router_key_checked=True;self.router_key_locked=bool(data.get('key_present') or data.get('configured'))
            self.router_key_usable=bool(data.get('configured'))
            self.router_key_editing=not self.router_key_locked;self.router_key.set('')
            self.router_key_notice.set('Sleutel toegevoegd. De waarde blijft verborgen.' if data['configured'] else 'Sleutel aanwezig, maar het formaat klopt niet. Kies Sleutel wijzigen.' if self.router_key_locked else 'Nog geen sleutel toegevoegd.')
            self.router_saved_model=data['model'];self.router_model.set(data['model'])
            self.router_private.set(data.get('data_collection','deny')=='deny');self.populate_router_choices()
            self.router_status.set('Kies en test hier je OpenRouter-model. Je actieve verwerking verandert pas als je dat zelf kiest.')
        self.request('/api/openrouter/status',loaded)

    def build_history(self):
        tab=self.tabs['history']
        page_header(tab,'Geschiedenis','Je teksten van de afgelopen 30 dagen. Alleen op deze pc.')
        row=ttk.Frame(tab,style='Page.TFrame');row.pack(fill='x',pady=(0,12))
        self.history_query=tk.StringVar();box,search=search_field(row,self.history_query,self.fonts,'Page.TFrame',hint='');box.pack(side='left',fill='x',expand=True)
        search.bind('<Return>',lambda _:self.load_history())
        ttk.Button(row,text='Zoeken',style='Primary.TButton',command=self.load_history).pack(side='left',padx=(8,0))
        listing=card(tab)
        self.history_tree=ttk.Treeview(listing,columns=('time','preview'),show='headings',height=8,selectmode='browse')
        self.history_tree.heading('time',text='Datum en tijd',anchor='w');self.history_tree.heading('preview',text='Tekst',anchor='w')
        self.history_tree.column('time',width=150,stretch=False);self.history_tree.column('preview',width=630)
        self.history_tree.pack(fill='x');self.history_tree.bind('<<TreeviewSelect>>',self.select_history)
        self.history_rows={};self.history_generation=0;self.history_offset=0
        ttk.Button(listing,text='Meer laden',style='Link.TButton',command=lambda:self.load_history(False)).pack(anchor='e',pady=(8,0))
        detail=card(tab,expand=True)
        head=ttk.Frame(detail);head.pack(fill='x')
        ttk.Label(head,text='Geselecteerde tekst',style='CardTitle.TLabel').pack(side='left')
        ttk.Button(head,text='Kopiëren',style='Primary.TButton',command=lambda:self.copy(self.history_text.get('1.0','end-1c'))).pack(side='right')
        self.history_text=text_box(detail,6);self.history_text.pack(fill='both',expand=True,pady=(10,6))
        self.history_raw=tk.StringVar();ttk.Label(detail,textvariable=self.history_raw,style='Muted.TLabel',wraplength=760).pack(anchor='w')

    def load_history(self,reset=True):
        if reset:
            self.history_generation+=1;self.history_offset=0;self.history_rows.clear()
            self.history_tree.delete(*self.history_tree.get_children())
            set_text(self.history_text,'');self.history_raw.set('')
        generation=self.history_generation;offset=self.history_offset
        def loaded(data,error):
            if error or generation!=self.history_generation:return
            for row in data['items']:
                self.history_rows[row['id']]=row
                if not self.history_tree.exists(row['id']):self.history_tree.insert('', 'end',iid=row['id'],values=(datetime.fromtimestamp(row['created_at']).astimezone().strftime('%d-%m-%Y %H:%M'),row['text'].replace('\n',' ')[:130]))
            self.history_offset=offset+len(data['items'])
            self.status.set(f"{data['total']} transcripties. {len(self.history_rows)} getoond. Alleen op deze pc.")
        self.request('/api/history?'+urlencode(dict(q=self.history_query.get(),limit=40,offset=offset)),loaded)

    def select_history(self,event=None):
        selected=self.history_tree.selection()
        if not selected:return
        row=self.history_rows[selected[0]];set_text(self.history_text,row['text'])
        self.history_raw.set('Oorspronkelijk: '+row['raw'][:220])

class LibraryEditor:
    def __init__(self,window,kind,tab):
        self.window=window;self.kind=kind;self.rows={};self.identifier=None;self.busy=False
        split=ttk.Panedwindow(tab,orient='horizontal');split.pack(fill='both',expand=True)
        left=ttk.Frame(split,style='Card.TFrame',padding=(16,14));right=ttk.Frame(split,style='Card.TFrame',padding=(20,16))
        split.add(left,weight=2);split.add(right,weight=3)
        self.search=tk.StringVar();row,search=search_field(left,self.search,window.fonts,hint='');row.pack(fill='x',pady=(0,10))
        self.search.trace_add('write',lambda *_:self.render())
        self.tree=ttk.Treeview(left,columns=('name',),show='headings',selectmode='browse');self.tree.heading('name',text='Snippet' if kind=='snippet' else 'Woord / juiste spelling',anchor='w');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        buttons=ttk.Frame(left);buttons.pack(fill='x',pady=(10,0))
        ttk.Button(buttons,text='Exporteren naar telefoon',command=self.export).pack(side='left')
        self.title=tk.StringVar();ttk.Label(right,textvariable=self.title,style='CardTitle.TLabel').pack(anchor='w',pady=(0,12))
        self.name=tk.StringVar()
        if kind=='snippet':
            ttk.Label(right,text='Naam').pack(anchor='w');ttk.Entry(right,textvariable=self.name).pack(fill='x',pady=(4,12))
        ttk.Label(right,text='Vaste tekst' if kind=='snippet' else 'Juiste spelling').pack(anchor='w')
        self.value=text_box(right,7 if kind=='snippet' else 2);self.value.pack(fill='both',expand=kind=='snippet',pady=(4,12))
        ttk.Label(right,text='Herkenningsvarianten, één per regel').pack(anchor='w')
        ttk.Label(right,text='Hoe Flow Lab het woord soms verkeerd hoort.' if kind!='snippet' else 'Wat je zegt om deze tekst te plaatsen.',style='Muted.TLabel').pack(anchor='w')
        self.aliases=text_box(right,5,10);self.aliases.pack(fill='x',pady=(4,12))
        self.enabled=tk.BooleanVar(value=True);ttk.Checkbutton(right,text='Actief',variable=self.enabled).pack(anchor='w')
        self.hint=tk.StringVar();ttk.Label(right,textvariable=self.hint,style='Muted.TLabel',wraplength=420).pack(anchor='w',pady=6)
        row=ttk.Frame(right);row.pack(fill='x',pady=(6,0))
        self.save_button=ttk.Button(row,text='Opslaan',style='Primary.TButton',command=self.save);self.save_button.pack(side='right')
        self.delete_button=ttk.Button(row,text='Verwijderen',command=self.delete);self.delete_button.pack(side='right',padx=8)
        self.new_button=ttk.Button(row,text='+ Nieuw',command=self.clear);self.new_button.pack(side='left')
        self.clear()

    def load(self):
        if self.busy:return
        def loaded(data,error):
            if error:return
            self.rows={r['id']:r for r in data['snippets' if self.kind=='snippet' else 'dictionary']};self.render()
            self.window.status.set(f'{len(self.rows)} '+('snippets' if self.kind=='snippet' else 'woorden en spellingregels')+' beschikbaar.')
        self.window.request('/api/library',loaded)

    def export(self):
        target=filedialog.asksaveasfilename(parent=self.window.root,title='Bibliotheek exporteren',initialdir=str(Path.home()/'Downloads'),
            initialfile='flow-lab-bibliotheek.json',defaultextension='.json',filetypes=[('JSON','*.json')])
        if not target:return
        def loaded(data,error):
            if error:self.window.status.set('Exporteren mislukt: '+error[:160]);return
            out=phone_library(data)
            Path(target).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
            self.window.status.set(f"{len(out['dictionary'])} woorden en {len(out['snippets'])} snippets opgeslagen in {Path(target).name}. Zet dit bestand op je telefoon en kies daar Woorden > Bibliotheek importeren.")
        self.window.request('/api/library',loaded)

    def render(self):
        if self.busy:return
        self.tree.delete(*self.tree.get_children());term=self.search.get().casefold()
        for row in self.rows.values():
            if term in (row['name']+' '+' '.join(row['aliases'])).casefold():self.tree.insert('','end',iid=row['id'],values=(row['name']+(' (uit)' if not row['enabled'] else '')+(' (geleerd)' if row['source']=='auto-learn' else ''),))

    def clear(self):
        if self.busy:return
        self.identifier=None;self.name.set('');set_text(self.value,'');set_text(self.aliases,'');self.enabled.set(True)
        self.title.set('Snippet toevoegen' if self.kind=='snippet' else 'Woord toevoegen');self.hint.set('')
        self.tree.selection_remove(*self.tree.selection())

    def select(self,event=None):
        if self.busy:return
        selected=self.tree.selection()
        if not selected:return
        row=self.rows[selected[0]];self.identifier=row['id'];self.name.set(row['name'])
        set_text(self.value,row['value']);set_text(self.aliases,'\n'.join(row['aliases']));self.enabled.set(row['enabled'])
        self.title.set('Snippet bewerken' if self.kind=='snippet' else 'Woord bewerken')
        self.hint.set('Spellinghint. Na zelf opslaan wordt dit een expliciete correctieregel.' if row['source']=='wispr-hint' else 'Witregels en volledige tekst blijven behouden.')

    def lock(self,value):
        self.busy=value
        for b in (self.save_button,self.new_button,self.delete_button):b.configure(state='disabled' if value else 'normal')
        self.value.configure(state='disabled' if value else 'normal');self.aliases.configure(state='disabled' if value else 'normal')

    def save(self):
        if self.busy:return
        data=entry_payload(self.kind,self.identifier,self.name.get(),self.value.get('1.0','end-1c'),self.aliases.get('1.0','end-1c'),self.enabled.get())
        self.lock(True)
        def saved(result,error):
            self.lock(False)
            if error:self.hint.set(error[:180]);return
            self.identifier=result['id'];self.hint.set('Opgeslagen. Werkt bij je volgende dictaat.');self.load()
        self.window.request('/api/library/'+self.kind,saved,'POST',data)

    def delete(self):
        if self.busy or not self.identifier:return
        if not messagebox.askyesno('Item verwijderen','Dit item uit Flow Lab verwijderen?',parent=self.window.root):return
        identifier=self.identifier;self.lock(True)
        def deleted(result,error):
            self.lock(False)
            if not error:self.clear();self.load()
        self.window.request('/api/library/'+self.kind+'/'+quote(identifier,safe=''),deleted,'DELETE')
