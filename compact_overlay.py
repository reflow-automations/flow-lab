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
        height=64 if detail else self.HEIGHT
        self.canvas.configure(width=width,height=height)
        self.root.geometry(f'{width}x{height}+{(self.root.winfo_screenwidth()-width)//2}+{self.root.winfo_screenheight()-height-58}')
        self.width=width;self.height=height

    def set_hover(self,value):
        self.hover=value;self.layout();self.draw()

    def configure(self,*,text):
        self.text=text
        self.layout()

    def click(self,event):
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

    def render(self,state,levels,locked=False):
        if state!=self.state:self.state=state;self.layout()
        self.levels=list(levels);self.locked=locked;self.draw()

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
            self.rounded(0,0,self.width-1,24,'#242b26')
            c.create_text(self.width/2,12,text=self.text[:67],fill='#e4e9e5',font=('Segoe UI',9))
