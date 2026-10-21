"""Small non-activating dictation pill; canvas renders only app-owned state."""
import math
import time
import tkinter as tk

class CompactOverlay:
    WIDTH=156
    HEIGHT=36
    TRANSPARENT='#ff00ff'
    def __init__(self,root,cancel,finish,copy):
        self.root=root;self.cancel=cancel;self.finish=finish;self.copy=copy
        self.text='';self.state='idle';self.locked=False;self.hover=False;self.levels=[]
        self.proposal=None;self.review=None;self.layout_key=None;self.render_key=None
        root.configure(bg=self.TRANSPARENT)
        root.attributes('-transparentcolor',self.TRANSPARENT)
        self.canvas=tk.Canvas(root,width=self.WIDTH,height=self.HEIGHT,bg=self.TRANSPARENT,highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>',self.click)
        self.canvas.bind('<Enter>',lambda e:self.set_hover(True))
        self.canvas.bind('<Leave>',lambda e:self.set_hover(False))
        self.layout()

    def layout(self):
        detail=self.hover or (self.state=='idle' and self.text not in ('','Ingevoegd','Geannuleerd'))
        width=350 if detail else self.WIDTH
        height=(96 if self.state=='idle' and len(self.text)>60 else 64) if detail else self.HEIGHT
        if self.proposal:width=420;height=154
        screen_width=self.root.winfo_screenwidth();screen_height=self.root.winfo_screenheight()
        key=(width,height,screen_width,screen_height)
        if key!=self.layout_key:
            self.canvas.configure(width=width,height=height)
            self.root.geometry(f'{width}x{height}+{(screen_width-width)//2}+{screen_height-height-58}')
            self.layout_key=key
        self.width=width;self.height=height

    def set_hover(self,value):
        if self.proposal or value==self.hover:return
        self.hover=value;self.layout();self.draw()

    def configure(self,*,text):
        if text==self.text:return
        self.text=text
        self.layout();self.draw()

    def click(self,event):
        if self.proposal and 73<=event.y<=106:
            action='accept' if 16<=event.x<=193 else 'ignore' if 205<=event.x<=404 else None
            if action and self.review:self.review(self.proposal,action)
            return
        x=event.x-(self.width-self.WIDTH)/2
        y=event.y-(self.height-self.HEIGHT)
        if y<0 or y>self.HEIGHT:return
        if x<35:self.cancel()
        elif x>self.WIDTH-35:
            if self.state in ('recording','starting'):self.finish()
            elif self.state=='idle':self.copy()

    def rounded(self,x,y,w,h,color,outline=None):
        r=h/2;c=self.canvas
        c.create_oval(x,y,x+h,y+h,fill=color,outline=outline or color)
        c.create_oval(x+w-h,y,x+w,y+h,fill=color,outline=outline or color)
        c.create_rectangle(x+r,y,x+w-r,y+h,fill=color,outline=color)

    def panel(self,w,h,color):
        c=self.canvas;r=12
        for x,y in ((0,0),(w-2*r,0),(0,h-2*r),(w-2*r,h-2*r)):
            c.create_oval(x,y,x+2*r,y+2*r,fill=color,outline=color)
        c.create_rectangle(r,0,w-r,h,fill=color,outline=color)
        c.create_rectangle(0,r,w,h-r,fill=color,outline=color)

    def render(self,state,levels,locked=False):
        if state!='idle' and self.proposal:self.clear_proposal()
        if state!=self.state:self.state=state;self.layout()
        self.levels=list(levels);self.locked=locked
        key=(state,tuple(self.levels) if state=='recording' else (),locked if state=='recording' else False)
        animated=state in ('processing','inserting','starting')
        if animated or key!=self.render_key:self.draw()
        self.render_key=key

    def offer(self,proposal,review):
        self.hover=False;self.proposal=proposal;self.review=review;self.layout();self.draw()

    def clear_proposal(self):
        self.hover=False;self.proposal=None;self.review=None;self.layout();self.draw()

    def draw(self):
        c=self.canvas;c.delete('all');offset=(self.width-self.WIDTH)/2
        self.rounded(offset+1,1,self.WIDTH-2,33,'#181d1b')
        c.create_oval(offset+7,7,offset+29,29,fill='#353b37',outline='')
        c.create_line(offset+14,14,offset+22,22,fill='#e4e8e5',width=1.5)
        c.create_line(offset+22,14,offset+14,22,fill='#e4e8e5',width=1.5)
        if self.state in ('processing','inserting','starting'):
            phase=(time.monotonic()*240)%360
            c.create_arc(offset+69,9,offset+87,27,start=phase,extent=230,style='arc',outline='#dde5df',width=2)
        elif self.state=='idle':
            c.create_text(offset+78,18,text='Klaar' if self.text=='Ingevoegd' else 'Flow Lab',fill='#e2e7e3',font=('Segoe UI',9))
        else:
            values=self.levels[-13:]
            values=[0.]*(13-len(values))+values
            for i,level in enumerate(values):
                h=3+min(1,max(0,level))*15
                c.create_line(offset+42+i*5,18-h/2,offset+42+i*5,18+h/2,fill='#e4eee6',width=2,capstyle='round')
            if self.locked:
                c.create_rectangle(offset+112,16,offset+119,23,outline='#9ed0ad',width=1)
                c.create_arc(offset+113,10,offset+118,19,start=0,extent=180,style='arc',outline='#9ed0ad')
        c.create_oval(offset+127,7,offset+149,29,fill='#e5ece6',outline='')
        c.create_line(offset+133,18,offset+137,22,offset+144,14,fill='#1d2b21',width=2)
        if self.height>self.HEIGHT:
            c.move('all',0,self.height-self.HEIGHT)
            detail_height=self.height-self.HEIGHT-4
            if self.proposal:self.panel(self.width-1,detail_height,'#242b26')
            else:self.rounded(0,0,self.width-1,detail_height,'#242b26')
            if self.proposal:
                hint=self.proposal['mode']=='hint';word=self.proposal['right']
                title=('Als spellinghint onthouden?' if hint else 'Deze correctie onthouden?')
                c.create_text(16,16,text=title,anchor='w',fill='#e4e9e5',font=('Segoe UI',10,'bold'))
                shorten=lambda value:value if len(value)<=30 else value[:27]+'...'
                c.create_text(16,44,text=word if hint else shorten(self.proposal['wrong'])+' → '+shorten(word),anchor='w',width=388,fill='#e4e9e5',font=('Segoe UI',10))
                for x,label,color in ((16,'Onthouden','#13a582'),(205,'Niet leren','#353b37')):
                    self.rounded(x,73,177 if x==16 else 199,33,color)
                    c.create_text(x+(177 if x==16 else 199)/2,89,text=label,fill='#ffffff',font=('Segoe UI',9))
                c.create_text(210,65,text='Geen vaste vervanging' if hint else 'Vaste vervanging voor deze schrijfwijze',fill='#aab9b0',font=('Segoe UI',8))
            else:c.create_text(self.width/2,detail_height/2,text=self.text,width=self.width-24,fill='#e4e9e5',font=('Segoe UI',9))
