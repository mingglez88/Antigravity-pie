"""Small native Tk controls with a restrained, rounded appearance."""
import tkinter as tk


def rounded(canvas, x, y, box_width, height, radius, **kwargs):
    width = box_width
    points = [x+radius,y, x+width-radius,y, x+width,y, x+width,y+radius,
              x+width,y+height-radius, x+width,y+height, x+width-radius,y+height,
              x+radius,y+height, x,y+height, x,y+height-radius, x,y+radius, x,y]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class PillButton(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=110, **kwargs):
        super().__init__(parent, width=width, height=38, bg=parent.cget('bg'),
                         highlightthickness=0, takefocus=True, cursor='hand2', **kwargs)
        self.text = text
        self.command = command
        self.primary = primary
        self.disabled = False
        self.hover = False
        self.bind('<Configure>', lambda event: self._draw())
        self.bind('<Enter>', lambda event: self._hover(True))
        self.bind('<Leave>', lambda event: self._hover(False))
        self.bind('<Button-1>', self._click)
        self.bind('<Return>', self._click)
        self.bind('<space>', self._click)
        self.bind('<FocusIn>', lambda event: self._draw())
        self.bind('<FocusOut>', lambda event: self._draw())
        self._draw()

    def configure(self, cnf=None, **kwargs):
        if 'state' in kwargs:
            self.disabled = kwargs.pop('state') == 'disabled'
        if 'text' in kwargs:
            self.text = kwargs.pop('text')
        super().configure(cnf, **kwargs)
        if hasattr(self, 'disabled'):
            self._draw()

    config = configure

    def _hover(self, value):
        self.hover = value
        self._draw()

    def _click(self, event=None):
        if not self.disabled:
            self.command()

    def _draw(self):
        self.delete('all')
        width = max(self.winfo_width(), int(self.cget('width')))
        fill = ('#0069da' if self.hover else '#007aff') if self.primary else ('#e5e5ea' if self.hover else '#f0f0f3')
        if self.disabled:
            fill = '#dce9fb' if self.primary else '#f2f2f4'
        color = '#ffffff' if self.primary else '#35353b'
        if self.disabled: color = '#919198'
        focused = self.focus_get() is self
        rounded(self, 1, 1, width-2, 36, 12, fill=fill,
                outline='#80b9ff' if focused else fill, width=2)
        self.create_text(width/2, 19, text=self.text, fill=color, font=('Microsoft YaHei UI', 10))


class Toggle(tk.Canvas):
    def __init__(self, parent, variable, command=None):
        super().__init__(parent, width=42, height=25, bg=parent.cget('bg'),
                         highlightthickness=0, cursor='hand2', takefocus=True)
        self.variable = variable
        self.command = command
        self.trace = variable.trace_add('write', lambda *args: self._draw())
        self.bind('<Button-1>', self._toggle)
        self.bind('<space>', self._toggle)
        self.bind('<Return>', self._toggle)
        self.bind('<Destroy>', self._destroy_trace)
        self._draw()

    def _destroy_trace(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self.trace)

    def _toggle(self, event=None):
        self.variable.set(not self.variable.get())
        if self.command: self.command()

    def _draw(self):
        self.delete('all')
        active = self.variable.get()
        rounded(self, 1, 2, 40, 22, 11, fill='#34c759' if active else '#d1d1d6', outline='')
        left = 20 if active else 3
        self.create_oval(left, 4, left+18, 22, fill='white', outline='#ffffff')


class Card(tk.Frame):
    def __init__(self, parent, padding=20):
        super().__init__(parent, bg=parent.cget('bg'))
        self.padding = padding
        self.canvas = tk.Canvas(self, bg=self.cget('bg'), highlightthickness=0, height=100)
        self.canvas.pack(fill=tk.X, expand=True)
        self.body = tk.Frame(self.canvas, bg='#ffffff')
        self.item = self.canvas.create_window(padding, padding, anchor='nw', window=self.body)
        self.body.bind('<Configure>', self._layout)
        self.canvas.bind('<Configure>', self._layout)

    def _layout(self, event=None):
        width = self.canvas.winfo_width()
        self.canvas.itemconfigure(self.item, width=max(1, width - 2*self.padding))
        height = self.body.winfo_reqheight() + 2*self.padding
        self.canvas.configure(height=height)
        self.canvas.delete('surface')
        rounded(self.canvas, 0, 0, width, height, 20, fill='#ffffff', outline='', tags='surface')
        self.canvas.tag_lower('surface')
