"""Native Windows management window. Uses the existing loopback API, no browser."""
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk,messagebox
from urllib.parse import urlencode,quote
import httpx
from shortcut_config import shortcut,shortcut_label,KEYS,MODIFIERS,LABELS
from model_guide import load_guide,guide_text

def entry_payload(kind,identifier,name,value,aliases,enabled):
    return dict(id=identifier or None,name=name if kind=='snippet' else value,
                value=value,aliases=[a.strip() for a in aliases.splitlines() if a.strip()],enabled=bool(enabled))

def set_text(widget,value):
    widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value)

class NativeApp:
    def __init__(self,app):
        self.app=app;self.root=tk.Toplevel(app.root);self.root.title('Flow Lab')
        self.model_guide=load_guide();self.guide_window=None
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
        for key,label in [('home','Dicteren'),('history','Geschiedenis'),('dictionary','Woordenboek'),('snippets','Snippets'),('settings','Instellingen'),('openrouter','OpenRouter'),('learning','Recent geleerd')]:
            tab=ttk.Frame(self.notebook,padding=18);self.tabs[key]=tab;self.notebook.add(tab,text=label)
        self.build_home();self.build_history();self.build_settings();self.build_openrouter()
        self.editors={kind:LibraryEditor(self,kind,self.tabs['snippets' if kind=='snippet' else 'dictionary']) for kind in ('dictionary','snippet')}
        self.build_learning()
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
        elif selected==str(self.tabs['openrouter']):self.load_openrouter_status()
        elif selected==str(self.tabs['learning']):self.refresh_learning()
        else:self.refresh_home()

    def build_settings(self):
        outer=self.tabs['settings']
        self.settings_canvas=tk.Canvas(outer,highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=self.settings_canvas.yview)
        scroll.pack(side='right',fill='y')
        self.settings_canvas.pack(side='left',fill='both',expand=True)
        self.settings_canvas.configure(yscrollcommand=scroll.set)
        tab=ttk.Frame(self.settings_canvas)
        item=self.settings_canvas.create_window(0,0,window=tab,anchor='nw')
        tab.bind('<Configure>',lambda _:self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox('all')))
        self.settings_canvas.bind('<Configure>',lambda event:self.settings_canvas.itemconfigure(item,width=event.width))
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
            'formatter':{'Volledig lokaal':'local','Lokale audio, cloudopmaak':'cloud-mini','Lokale audio, OpenRouter gratis':'openrouter-free'},
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
        self.settings_model_hint=tk.StringVar()
        ttk.Label(options,textvariable=self.settings_model_hint,wraplength=300,justify='left').grid(row=0,column=2,rowspan=3,sticky='nw',padx=(24,0))
        ttk.Button(options,text='Welke modellen kies ik?',command=self.show_model_guide).grid(row=3,column=2,sticky='w',padx=(24,0),pady=(9,0))
        ttk.Button(tab,text='OpenRouter instellen (optioneel)',command=lambda:self.show('openrouter')).pack(anchor='w',pady=(0,8))
        self.learning_enabled=tk.BooleanVar(value=self.app.config.get('auto_learn',False))
        ttk.Checkbutton(tab,text='Automatisch leren van mijn woordcorrecties',variable=self.learning_enabled,
                        command=lambda:self.app.events.put(('learning_toggle',self.learning_enabled.get()))).pack(anchor='w')
        ttk.Label(tab,text='Verbeter binnen een minuut in hetzelfde tekstvak. Na 1,5 seconde rust wordt een duidelijke correctie beoordeeld.',wraplength=850).pack(anchor='w',pady=(3,6))
        ttk.Button(tab,text='Recent geleerde correcties bekijken',command=lambda:self.show('learning')).pack(anchor='w',pady=(0,6))
        def explain_settings(*_):
            selected=self.preference_choices['formatter'].get(self.preference_vars['formatter'].get(),'local')
            self.settings_model_hint.set(self.model_guide['desktop'][selected])
        self.preference_vars['formatter'].trace_add('write',explain_settings);explain_settings()
        ttk.Label(tab,text='Volledig lokaal houdt audio en tekst op deze pc. Audio blijft 24 uur versleuteld bewaard voor opnieuw verwerken.\nBij cloudopmaak gaat alleen de herkende tekst naar de gekozen provider.',wraplength=850).pack(anchor='w')

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
        ttk.Label(tab,text='Jouw schrijfwijzen leren',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Duidelijke correcties naar bekende namen worden onthouden. Nieuwe woorden vragen herhaling; twijfelgevallen blijven een voorstel.\nJe kunt hier aannemen, negeren of alleen de geleerde wijziging ongedaan maken.',wraplength=850).pack(anchor='w',pady=(8,12))
        self.learning_status=tk.StringVar(value='Correcties worden lokaal beoordeeld. Volledige tekstvelden worden niet opgeslagen.')
        ttk.Label(tab,textvariable=self.learning_status,wraplength=850).pack(anchor='w',pady=(0,10))
        self.learning_rows={}
        self.learning_tree=ttk.Treeview(tab,columns=('wrong','right','state','count'),show='headings',selectmode='browse')
        for key,label,width in [('wrong','Gehoorde schrijfwijze',235),('right','Jouw correctie',235),('state','Status',160),('count','Dictaten',70)]:
            self.learning_tree.heading(key,text=label);self.learning_tree.column(key,width=width)
        self.learning_tree.pack(fill='both',expand=True)
        self.learning_tree.bind('<<TreeviewSelect>>',lambda _:self.learning_selection())
        self.learning_detail=tk.StringVar();ttk.Label(tab,textvariable=self.learning_detail,wraplength=850).pack(anchor='w',pady=10)
        buttons=ttk.Frame(tab);buttons.pack(fill='x')
        self.learning_buttons={}
        for action,label in [('accept','Onthouden'),('ignore','Negeren'),('undo','Ongedaan maken')]:
            button=ttk.Button(buttons,text=label,command=lambda a=action:self.review_learning(a),state='disabled')
            button.pack(side='left',padx=(0,8));self.learning_buttons[action]=button
        ttk.Button(buttons,text='Vernieuwen',command=self.load_learning).pack(side='right')

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
        self.shortcut_text=tk.StringVar();ttk.Label(tab,textvariable=self.shortcut_text,font=('Segoe UI',16,'bold')).pack(anchor='w',pady=(4,14))
        ttk.Label(tab,text='Houd ingedrukt om te spreken. Laat los om te verwerken en te plaatsen.\nTwee keer snel indrukken zet de opname vast; nogmaals drukken stopt.\nKlik eerst in het tekstvak waar je de tekst wilt hebben. Maximaal 5 minuten.',font=('Segoe UI',11),justify='left').pack(anchor='w')
        self.replay_text=tk.StringVar();ttk.Label(tab,textvariable=self.replay_text).pack(anchor='w',pady=(12,18))
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Label(row,text='Verwerking:').pack(side='left',padx=(0,10))
        self.mode_choices={'Volledig lokaal':'local','Lokale audio, cloudopmaak':'cloud-mini','Lokale audio, OpenRouter gratis':'openrouter-free'}
        self.mode=tk.StringVar(value=next(name for name,value in self.mode_choices.items() if value==self.app.config['formatter']))
        choice=ttk.Combobox(row,textvariable=self.mode,values=list(self.mode_choices),state='readonly',width=31)
        choice.pack(side='left');choice.bind('<<ComboboxSelected>>',lambda _:self.app.events.put(('mode',self.mode_choices[self.mode.get()])))
        ttk.Button(row,text='Welke modellen kies ik?',command=self.show_model_guide).pack(side='left',padx=12)
        self.home_model_hint=tk.StringVar()
        def explain_home(*_):self.home_model_hint.set(self.model_guide['desktop'][self.mode_choices[self.mode.get()]])
        self.mode.trace_add('write',explain_home);explain_home()
        ttk.Label(tab,textvariable=self.home_model_hint,wraplength=820).pack(anchor='w',pady=(8,20))
        recovery=ttk.LabelFrame(tab,text='Opnames van de afgelopen 24 uur',padding=8);recovery.pack(fill='x',pady=(0,12))
        self.recovery_hint=tk.StringVar(value='Geen opname klaar voor herstel.')
        ttk.Label(recovery,textvariable=self.recovery_hint,wraplength=820).pack(anchor='w')
        actions=ttk.Frame(recovery);actions.pack(fill='x',pady=(6,0))
        self.recovery_choice=tk.StringVar();self.recovery_choices={}
        self.recovery_combo=ttk.Combobox(actions,textvariable=self.recovery_choice,state='readonly',width=47)
        self.recovery_combo.pack(side='left',fill='x',expand=True)
        self.retry_button=ttk.Button(actions,text='Opnieuw verwerken',command=self.retry_selected)
        self.retry_button.pack(side='left',padx=8)
        self.discard_button=ttk.Button(actions,text='Opname verwijderen',command=self.discard_selected)
        self.discard_button.pack(side='left')
        ttk.Label(tab,text='Kopie van laatste resultaat',font=('Segoe UI',12,'bold')).pack(anchor='w')
        self.insertion_message=tk.StringVar(value=getattr(self.app,'last_insertion_message',''))
        ttk.Label(tab,textvariable=self.insertion_message,wraplength=850).pack(anchor='w',pady=(4,0))
        self.latest=tk.Text(tab,height=8,wrap='word',font=('Segoe UI',11),padx=12,pady=12)
        self.latest.pack(fill='both',expand=True,pady=8)
        ttk.Button(tab,text='Laatste resultaat kopiëren',command=lambda:self.copy(self.latest.get('1.0','end-1c'))).pack(anchor='e')

    def show_model_guide(self):
        if self.guide_window and self.guide_window.winfo_exists():self.guide_window.lift();return
        dialog=tk.Toplevel(self.root);self.guide_window=dialog
        dialog.title('Flow Lab - Welke modellen kies ik?');dialog.geometry('790x650');dialog.minsize(620,450);dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=18);frame.pack(fill='both',expand=True)
        text=tk.Text(frame,wrap='word',font=('Segoe UI',11),padx=14,pady=14,background='#f8faf8',relief='flat')
        scroll=ttk.Scrollbar(frame,command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0',guide_text(self.model_guide));text.configure(state='disabled')
        ttk.Button(dialog,text='Sluiten',command=dialog.destroy).pack(pady=(0,12))

    def refresh_home(self):
        store=getattr(self.app,'recovery_store',None)
        entries=store.entries() if store else []
        self.recovery_choices={f"{datetime.fromtimestamp(item['created_at']).strftime('%d-%m %H:%M:%S')} | {item['duration_s']:.0f} s | {item.get('config',{}).get('formatter','onleesbaar')}"+(" | gedeeltelijk" if item.get('partial') else ''):item['id'] for item in entries}
        self.recovery_combo.configure(values=list(self.recovery_choices))
        if self.recovery_choice.get() not in self.recovery_choices:self.recovery_choice.set(next(iter(self.recovery_choices),''))
        enabled=bool(entries) and getattr(self.app,'state','idle')=='idle'
        self.retry_button.configure(state='normal' if enabled else 'disabled');self.discard_button.configure(state='normal' if enabled else 'disabled')
        self.recovery_hint.set('Audio blijft 24 uur versleuteld bewaard, ook na succes. Maximaal 500 MB. Opnieuw verwerken gebruikt de oorspronkelijke modelkeuze.' if entries else 'Nog geen bewaarde opname. Nieuwe desktopopnames blijven hier 24 uur beschikbaar, ook na herstart.')
        if any(not item.get('persistent',True) for item in entries):self.recovery_hint.set('Let op: herstelkopie alleen in geheugen. Sluit Flow Lab niet voordat je deze hebt hersteld.')
        self.insertion_message.set(getattr(self.app,'last_insertion_message',''))
        self.shortcut_text.set(shortcut_label(self.app.config['hotkey'])+'  |  Dicteren')
        import desktop_windows as w
        key=w.REPLAY_KEYS.get(self.app.replay_key,(None,None,'Geen vrije sneltoets'))[2]
        self.replay_text.set(key+'  |  Laatste tekst opnieuw plaatsen')
        self.mode.set(next(name for name,value in self.mode_choices.items() if value==self.app.config['formatter']))
        def status(data,error):
            if not error:self.status.set('Lokale verwerking actief. '+('Er wordt momenteel verwerkt.' if data['busy'] else 'Klaar om te dicteren.'))
        self.request('/api/status',status)
        def latest(data,error):
            if not error:
                set_text(self.latest,data['items'][0]['text'] if data['items'] else '')
                self.latest.configure(state='disabled')
        self.request('/api/history?limit=1',latest)

    def retry_selected(self):
        key=self.recovery_choices.get(self.recovery_choice.get())
        if key:
            self.retry_button.configure(state='disabled');self.discard_button.configure(state='disabled')
            self.app.events.put(('retry_recording',key))

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
        tab=self.tabs['openrouter'];self.router_models=[]
        ttk.Label(tab,text='OpenRouter: gratis tekstopmaak uitproberen',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Audio blijft lokaal. Herkende tekst gaat via OpenRouter naar de gekozen provider.\nGratis modellen kunnen druk of tijdelijk niet beschikbaar zijn. Lokaal blijft de standaard.',wraplength=870).pack(anchor='w',pady=10)
        self.router_status=tk.StringVar(value='Nog niet gecontroleerd.');ttk.Label(tab,textvariable=self.router_status,wraplength=870).pack(anchor='w',pady=(0,10))
        row=ttk.Frame(tab);row.pack(fill='x')
        self.router_key=tk.StringVar();ttk.Entry(row,textvariable=self.router_key,show='*',width=55).pack(side='left',fill='x',expand=True)
        def save_key():
            key=self.router_key.get().strip();self.router_key.set('')
            def saved(data,error):
                self.router_status.set(error if error else 'Sleutel versleuteld opgeslagen voor je Windows-account.')
                if not error:self.load_openrouter_status()
            self.request('/api/openrouter/key',saved,'POST',{'key':key})
        ttk.Button(row,text='Sleutel veilig opslaan',command=save_key).pack(side='left',padx=8)
        ttk.Label(tab,text='De opgeslagen sleutel wordt niet teruggetoond. Je kunt ook OPENROUTER_API_KEY in .env.local gebruiken.').pack(anchor='w',pady=(6,14))
        self.router_model=tk.StringVar();self.router_combo=ttk.Combobox(tab,textvariable=self.router_model,state='readonly',width=82);self.router_combo.pack(fill='x')
        buttons=ttk.Frame(tab);buttons.pack(fill='x',pady=10)
        def models():
            self.router_status.set('Actuele gratis modellen ophalen...')
            def loaded(data,error):
                if error:self.router_status.set(error);return
                self.router_models=data['models'];ids=[m['id'] for m in self.router_models];self.router_combo.configure(values=ids)
                if self.router_model.get() not in ids:self.router_model.set('')
                self.router_status.set(f'{len(ids)} gratis tekstmodellen gevonden. Kies er één en sla de modelkeuze op.')
            self.request('/api/openrouter/models?refresh=true',loaded)
        def save_model():
            def saved(data,error):self.router_status.set(error if error else 'Model opgeslagen. Kies bij Verwerking OpenRouter gratis om het te gebruiken.')
            self.request('/api/openrouter/model',saved,'POST',{'model':self.router_model.get()})
        def check():
            def checked(data,error):
                if error:self.router_status.set(error);return
                q=data['free_requests'];self.router_status.set('Sleutel geldig. Gratis verzoeken resterend vandaag: '+str(q.get('remaining') if q.get('remaining') is not None else 'niet opgegeven')+' (daglimiet '+str(q.get('limit') if q.get('limit') is not None else 'onbekend')+').')
            self.request('/api/openrouter/check',checked,'POST')
        for label,fn in [('Gratis modellen ophalen',models),('Modelkeuze opslaan',save_model),('Sleutel / quotum controleren',check)]:ttk.Button(buttons,text=label,command=fn).pack(side='left',padx=(0,8))
        self.router_private=tk.BooleanVar(value=True)
        privacy_row=ttk.Frame(tab);privacy_row.pack(fill='x')
        ttk.Checkbutton(privacy_row,text='Alleen providers zonder gegevensverzameling',variable=self.router_private).pack(side='left')
        def save_privacy():
            def saved(data,error):self.router_status.set(error if error else 'Privacykeuze opgeslagen. Je OpenRouter-accountbeleid blijft ook gelden.')
            self.request('/api/openrouter/privacy',saved,'POST',{'data_collection':'deny' if self.router_private.get() else 'allow'})
        ttk.Button(privacy_row,text='Privacykeuze opslaan',command=save_privacy).pack(side='left',padx=10)
        ttk.Label(tab,text='Als je dit uitzet, kunnen providers je tekst bewaren of voor training gebruiken volgens hun voorwaarden.\nAlleen :free-modellen met nultarief; geen betaald alternatief of willekeurige router.\nEén lang dictaat kan meerdere verzoeken gebruiken. De daglimiet is dus geen aantal dictaten.',wraplength=870).pack(anchor='w',pady=(4,12))
        def test():
            self.router_status.set('Test met vaste, verzonnen tekst. Er wordt geen opname gebruikt...')
            def tested(data,error):
                if error:self.router_status.set(error);return
                set_text(self.router_result,data['text'])
                self.router_status.set(f"Test klaar in {data['ms']/1000:.2f} s. "+(data.get('warning') or 'Beoordeel ook de inhoud; dit is één korte proef.'))
            self.request('/api/openrouter/test',tested,'POST')
        ttk.Button(tab,text='Snelheid testen met voorbeeldtekst',command=test).pack(anchor='w')
        self.router_result=tk.Text(tab,height=5,wrap='word',font=('Segoe UI',10),padx=8,pady=8);self.router_result.pack(fill='both',expand=True,pady=8)

    def load_openrouter_status(self):
        def loaded(data,error):
            if error:self.router_status.set(error);return
            self.router_model.set(data['model'])
            self.router_private.set(data.get('data_collection','deny')=='deny')
            key_message='Sleutel aanwezig.' if data['configured'] else ('De ingevulde waarde heeft geen OpenRouter-formaat.' if data.get('key_present') else 'Voeg je eigen OpenRouter-sleutel toe.')
            self.router_status.set(key_message+' Alleen gratis modellen; standaardverwerking blijft ongewijzigd.')
        self.request('/api/openrouter/status',loaded)

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
