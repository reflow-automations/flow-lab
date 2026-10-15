"""Native Windows management window. Uses the existing loopback API, no browser."""
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk,messagebox
from urllib.parse import urlencode,quote
import httpx
from shortcut_config import shortcut,shortcut_label,KEYS,MODIFIERS,LABELS

def entry_payload(kind,identifier,name,value,aliases,enabled):
    return dict(id=identifier or None,name=name if kind=='snippet' else value,
                value=value,aliases=[a.strip() for a in aliases.splitlines() if a.strip()],enabled=bool(enabled))

def set_text(widget,value):
    widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value)

class NativeApp:
    def __init__(self,app):
        self.app=app;self.root=tk.Toplevel(app.root);self.root.title('Flow Lab')
        self.root.geometry('1060x740');self.root.minsize(820,600)
        self.root.iconbitmap(str(app.root_path/'assets/flow-lab.ico'))
        self.root.update_idletasks()
        import desktop_windows as w
        hwnd=w.ancestor(self.root.winfo_id(),2)
        w.set_style(hwnd,-20,(w.get_style(hwnd,-20)|0x40000)&~0x80)
        self.root.protocol('WM_DELETE_WINDOW',self.hide)
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('Flow.TFrame',background='#eef4ef')
        style.configure('Flow.TLabel',background='#eef4ef',foreground='#1c3c30',font=('Segoe UI',10))
        style.configure('Flow.Title.TLabel',background='#eef4ef',foreground='#183e33',font=('Segoe UI',23,'bold'))
        style.configure('Flow.TButton',padding=(12,7),font=('Segoe UI',10))
        style.configure('Treeview',rowheight=29,font=('Segoe UI',10))
        shell=ttk.Frame(self.root,style='Flow.TFrame',padding=22);shell.pack(fill='both',expand=True)
        header=ttk.Frame(shell,style='Flow.TFrame');header.pack(fill='x')
        ttk.Label(header,text='Flow Lab',style='Flow.Title.TLabel').pack(side='left')
        ttk.Button(header,text='Sneltoets instellen',style='Flow.TButton',command=app.shortcut_settings).pack(side='right')
        ttk.Label(shell,text='Spreken, opmaken en terugvinden. Op jouw pc.',style='Flow.TLabel').pack(anchor='w',pady=(3,18))
        self.notebook=ttk.Notebook(shell);self.notebook.pack(fill='both',expand=True)
        self.tabs={}
        for key,label in [('home','Dicteren'),('history','Geschiedenis'),('dictionary','Woordenboek'),('snippets','Snippets'),('settings','Instellingen')]:
            tab=ttk.Frame(self.notebook,padding=18);self.tabs[key]=tab;self.notebook.add(tab,text=label)
        self.build_home();self.build_history();self.build_settings()
        self.editors={kind:LibraryEditor(self,kind,self.tabs['snippets' if kind=='snippet' else 'dictionary']) for kind in ('dictionary','snippet')}
        self.status=tk.StringVar(value='Verbinden met de lokale verwerking...')
        ttk.Label(shell,textvariable=self.status,style='Flow.TLabel').pack(anchor='w',pady=(12,4))
        footer=ttk.Frame(shell,style='Flow.TFrame');footer.pack(fill='x')
        ttk.Label(footer,text='Het kruisje verbergt dit venster; dicteren blijft dan actief.',style='Flow.TLabel').pack(side='left')
        ttk.Button(footer,text='Flow Lab volledig afsluiten',command=app.quit_all).pack(side='right')
        self.notebook.bind('<<NotebookTabChanged>>',lambda _:self.refresh_selected())
        self.show('home')

    def exists(self):return bool(self.root.winfo_exists())

    def request(self,path,callback,method='GET',data=None):
        def task():
            try:
                response=httpx.request(method,self.app.service_url+path,json=data,
                    headers={'Origin':self.app.service_url},timeout=8)
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
        self.notebook.select(self.tabs[panel]);self.root.deiconify();self.root.lift()
        self.refresh_selected();self.app.write_state()

    def hide(self):
        self.root.withdraw();self.app.write_state()

    def refresh_selected(self):
        selected=self.notebook.select()
        if selected==str(self.tabs['history']):self.load_history()
        elif selected==str(self.tabs['dictionary']):self.editors['dictionary'].load()
        elif selected==str(self.tabs['snippets']):self.editors['snippet'].load()
        elif selected==str(self.tabs['settings']):self.refresh_settings()
        else:self.refresh_home()

    def build_settings(self):
        tab=self.tabs['settings']
        shortcuts=ttk.LabelFrame(tab,text='Sneltoetsen',padding=14);shortcuts.pack(fill='x')
        self.settings_status=tk.StringVar();ttk.Label(shortcuts,textvariable=self.settings_status).pack(anchor='w')
        row=ttk.Frame(shortcuts);row.pack(fill='x',pady=12)
        _,mask,vk,_=shortcut(self.app.config['hotkey'])
        self.modifier_vars={k:tk.BooleanVar(value=bool(mask&flag)) for k,flag in MODIFIERS.items()}
        for k in MODIFIERS:ttk.Checkbutton(row,text=LABELS[k],variable=self.modifier_vars[k]).pack(side='left',padx=(0,14))
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
        ttk.Button(buttons,text='Ctrl+Windows kiezen',command=preset).pack(side='left')
        ttk.Button(buttons,text='Sneltoets opslaan',command=save_key).pack(side='left',padx=8)
        self.settings_replay=tk.StringVar();ttk.Label(shortcuts,textvariable=self.settings_replay).pack(anchor='w',pady=(10,3))
        ttk.Label(shortcuts,text='Houd ingedrukt om te spreken; dubbel indrukken vergrendelt.\nSneltoetsen zijn gepauzeerd zolang dit tabblad openstaat. Ga daarna naar Dicteren.\nSluit Wispr zelf als je dezelfde combinatie gebruikt.',justify='left').pack(anchor='w')
        options=ttk.LabelFrame(tab,text='Tekstverwerking',padding=14);options.pack(fill='x',pady=14)
        self.preference_vars={};self.preference_choices={
            'formatter':{'Volledig lokaal':'local','Lokale audio, cloudopmaak':'cloud-mini'},
            'paragraphs':{'Natuurlijk':'normaal','Meer witregels':'ruim','Alleen modelopmaak':'compact'},
            'style':{'Natuurlijk bericht':'bericht','Notitie of opsomming':'notitie','Woorden behouden':'letterlijk'}}
        for index,(key,label) in enumerate([('formatter','Verwerking'),('paragraphs',"Alinea's"),('style','Schrijfstijl')]):
            ttk.Label(options,text=label).grid(row=index,column=0,sticky='w',padx=(0,20),pady=5)
            mapping=self.preference_choices[key];value=self.app.config.get(key,{'style':'bericht','paragraphs':'normaal','formatter':'local'}[key])
            var=tk.StringVar(value=next((name for name,item in mapping.items() if item==value),next(iter(mapping))))
            self.preference_vars[key]=var
            ttk.Combobox(options,textvariable=var,values=list(mapping),state='readonly',width=33).grid(row=index,column=1,sticky='w',pady=5)
        def save_preferences():
            data={key:self.preference_choices[key][var.get()] for key,var in self.preference_vars.items()}
            self.app.events.put(('preferences',data))
        ttk.Button(options,text='Verwerking opslaan',command=save_preferences).grid(row=3,column=1,sticky='w',pady=(9,0))
        ttk.Label(tab,text='Volledig lokaal stuurt geen audio of tekst naar OpenAI. Bij cloudopmaak gaat alleen de herkende tekst naar OpenAI.\nInstellingen en geschiedenis blijven op deze pc; audio wordt niet bewaard.',wraplength=850).pack(anchor='w')

    def refresh_settings(self):
        self.settings_status.set('Actieve dicteersneltoets: '+shortcut_label(self.app.config['hotkey']))
        for key,var in self.preference_vars.items():
            value=self.app.config.get(key,{'style':'bericht','paragraphs':'normaal','formatter':'local'}[key])
            var.set(next((name for name,item in self.preference_choices[key].items() if item==value),next(iter(self.preference_choices[key]))))
        import desktop_windows as w
        replay=w.REPLAY_KEYS.get(self.app.replay_key,(None,None,'Niet beschikbaar'))[2]
        self.settings_replay.set('Laatste resultaat opnieuw plaatsen: '+replay)

    def build_home(self):
        tab=self.tabs['home']
        self.shortcut_text=tk.StringVar();ttk.Label(tab,textvariable=self.shortcut_text,font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(4,14))
        ttk.Label(tab,text='Houd ingedrukt om te spreken. Laat los om te verwerken en te plaatsen.\nTwee keer snel indrukken zet de opname vast; nogmaals drukken stopt.\nKlik eerst in het tekstvak waar je de tekst wilt hebben.',font=('Segoe UI',11),justify='left').pack(anchor='w')
        self.replay_text=tk.StringVar();ttk.Label(tab,textvariable=self.replay_text).pack(anchor='w',pady=(12,18))
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Label(row,text='Verwerking:').pack(side='left',padx=(0,10))
        self.mode=tk.StringVar(value='Volledig lokaal' if self.app.config['formatter']=='local' else 'Lokale audio, cloudopmaak')
        choice=ttk.Combobox(row,textvariable=self.mode,values=['Volledig lokaal','Lokale audio, cloudopmaak'],state='readonly',width=29)
        choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda _:self.app.events.put(('mode','local' if self.mode.get()=='Volledig lokaal' else 'cloud-mini')))
        ttk.Label(tab,text='Bij cloudopmaak gaat herkende tekst naar OpenAI. Audio blijft bij deze desktopopties lokaal.',wraplength=820).pack(anchor='w',pady=(8,20))
        ttk.Label(tab,text='Laatste resultaat',font=('Segoe UI',12,'bold')).pack(anchor='w')
        self.latest=tk.Text(tab,height=8,wrap='word',font=('Segoe UI',11),padx=12,pady=12)
        self.latest.pack(fill='both',expand=True,pady=8)
        ttk.Button(tab,text='Laatste resultaat kopiëren',command=lambda:self.copy(self.latest.get('1.0','end-1c'))).pack(anchor='e')

    def refresh_home(self):
        self.shortcut_text.set(shortcut_label(self.app.config['hotkey'])+'  |  Dicteren')
        import desktop_windows as w
        key=w.REPLAY_KEYS.get(self.app.replay_key,(None,None,'Geen vrije sneltoets'))[2]
        self.replay_text.set(key+'  |  Laatste tekst opnieuw plaatsen')
        self.mode.set('Volledig lokaal' if self.app.config['formatter']=='local' else 'Lokale audio, cloudopmaak')
        def status(data,error):
            if not error:self.status.set('Lokale verwerking actief. '+('Er wordt momenteel verwerkt.' if data['busy'] else 'Klaar om te dicteren.'))
        self.request('/api/status',status)
        def latest(data,error):
            if not error:set_text(self.latest,data['items'][0]['text'] if data['items'] else '')
        self.request('/api/history?limit=1',latest)

    def copy(self,text):
        if not text:return
        import desktop_windows as w
        try:w.copy_text(self.app.hwnd,text);self.status.set('Tekst gekopieerd.')
        except Exception:self.status.set('Klembord is bezet. Probeer opnieuw.')

    def build_history(self):
        tab=self.tabs['history'];row=ttk.Frame(tab);row.pack(fill='x')
        self.history_query=tk.StringVar();search=ttk.Entry(row,textvariable=self.history_query);search.pack(side='left',fill='x',expand=True)
        search.bind('<Return>',lambda _:self.load_history())
        ttk.Button(row,text='Zoeken / vernieuwen',command=self.load_history).pack(side='left',padx=8)
        self.history_tree=ttk.Treeview(tab,columns=('time','preview'),show='headings',height=7,selectmode='browse')
        self.history_tree.heading('time',text='Datum en tijd');self.history_tree.heading('preview',text='Tekst')
        self.history_tree.column('time',width=155,stretch=False);self.history_tree.column('preview',width=630)
        self.history_tree.pack(fill='x',pady=12);self.history_tree.bind('<<TreeviewSelect>>',self.select_history)
        self.history_rows={};self.history_generation=0;self.history_offset=0
        ttk.Button(tab,text='Meer laden',command=lambda:self.load_history(False)).pack(anchor='e')
        ttk.Label(tab,text='Geselecteerde transcriptie (maximaal 30 dagen bewaard)').pack(anchor='w')
        self.history_text=tk.Text(tab,height=8,wrap='word',font=('Segoe UI',11),padx=10,pady=10);self.history_text.pack(fill='both',expand=True,pady=7)
        self.history_raw=tk.StringVar();ttk.Label(tab,textvariable=self.history_raw,wraplength=850).pack(anchor='w')
        ttk.Button(tab,text='Transcriptie kopiëren',command=lambda:self.copy(self.history_text.get('1.0','end-1c'))).pack(anchor='e')

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
        left=ttk.Frame(split,padding=(0,0,16,0));right=ttk.Frame(split);split.add(left,weight=2);split.add(right,weight=3)
        self.search=tk.StringVar();ttk.Label(left,text='Zoeken').pack(anchor='w')
        ttk.Entry(left,textvariable=self.search).pack(fill='x',pady=(5,10));self.search.trace_add('write',lambda *_:self.render())
        self.tree=ttk.Treeview(left,columns=('name',),show='headings',selectmode='browse');self.tree.heading('name',text='Snippet' if kind=='snippet' else 'Woord / juiste spelling');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        ttk.Button(left,text='Vernieuwen',command=self.load).pack(anchor='w',pady=10)
        self.title=tk.StringVar();ttk.Label(right,textvariable=self.title,font=('Segoe UI',14,'bold')).pack(anchor='w',pady=(0,12))
        self.name=tk.StringVar()
        if kind=='snippet':
            ttk.Label(right,text='Naam').pack(anchor='w');ttk.Entry(right,textvariable=self.name).pack(fill='x',pady=(4,10))
        ttk.Label(right,text='Vaste tekst' if kind=='snippet' else 'Juiste spelling').pack(anchor='w')
        self.value=tk.Text(right,height=7 if kind=='snippet' else 2,wrap='word',font=('Segoe UI',11),padx=8,pady=8);self.value.pack(fill='both',expand=kind=='snippet',pady=(4,10))
        ttk.Label(right,text='Herkenningsvarianten, één per regel').pack(anchor='w')
        self.aliases=tk.Text(right,height=5,wrap='word',font=('Segoe UI',10),padx=8,pady=8);self.aliases.pack(fill='x',pady=(4,10))
        self.enabled=tk.BooleanVar(value=True);ttk.Checkbutton(right,text='Actief',variable=self.enabled).pack(anchor='w')
        self.hint=tk.StringVar();ttk.Label(right,textvariable=self.hint,wraplength=420).pack(anchor='w',pady=6)
        row=ttk.Frame(right);row.pack(fill='x',pady=10)
        self.new_button=ttk.Button(row,text='Nieuw',command=self.clear);self.new_button.pack(side='left')
        self.save_button=ttk.Button(row,text='Opslaan',command=self.save);self.save_button.pack(side='right')
        self.delete_button=ttk.Button(row,text='Verwijderen',command=self.delete);self.delete_button.pack(side='right',padx=8)
        self.clear()

    def load(self):
        if self.busy:return
        def loaded(data,error):
            if error:return
            self.rows={r['id']:r for r in data['snippets' if self.kind=='snippet' else 'dictionary']};self.render()
            self.window.status.set(f'{len(self.rows)} '+('snippets' if self.kind=='snippet' else 'woorden en spellingregels')+' beschikbaar.')
        self.window.request('/api/library',loaded)

    def render(self):
        if self.busy:return
        self.tree.delete(*self.tree.get_children());term=self.search.get().casefold()
        for row in self.rows.values():
            if term in (row['name']+' '+' '.join(row['aliases'])).casefold():self.tree.insert('','end',iid=row['id'],values=(row['name']+(' (uit)' if not row['enabled'] else ''),))

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
