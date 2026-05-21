"""StatusStrip — thin always-visible top bar with PLC-specific status info.

Tells investors at a glance: "this is an industrial automation IDE, not
a generic code editor". Shows: project name, runtime URI, PLC state with
LED color, task cycle time, last build result. Polls the
ProjectController once a second via wx.Timer.
"""

import wx


COLOR_BG       = wx.Colour(238, 240, 243)
COLOR_BORDER   = wx.Colour(208, 211, 218)
COLOR_INK      = wx.Colour(32, 34, 40)
COLOR_DIM      = wx.Colour(120, 124, 132)
COLOR_ACCENT   = wx.Colour(222, 140, 30)   # industrial amber
COLOR_RUN      = wx.Colour(46, 158, 68)    # green LED
COLOR_STOP     = wx.Colour(140, 142, 150)  # grey LED
COLOR_BROKEN   = wx.Colour(200, 40, 40)    # red LED


class _LED(wx.Panel):
    """Tiny circular LED indicator (6px)."""

    def __init__(self, parent, color=COLOR_STOP):
        super().__init__(parent, size=(10, 10))
        self._color = color
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(COLOR_BG)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.Refresh()

    def _on_paint(self, _e):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(COLOR_BG))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        gc.SetBrush(wx.Brush(self._color))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawEllipse(2, 2, 6, 6)
        # subtle glow
        gc.SetBrush(wx.Brush(wx.Colour(self._color.Red(), self._color.Green(),
                                       self._color.Blue(), 60)))
        gc.DrawEllipse(0, 0, 10, 10)


class StatusStrip(wx.Panel):
    def __init__(self, parent, project_controller_getter, frame_getter=None):
        super().__init__(parent, size=(-1, 26))
        self._get_ctr = project_controller_getter
        # Lets the strip read the active editor tab (current POU + language).
        # Optional so the strip still works if wired without a frame.
        self._get_frame = frame_getter or (lambda: None)
        # AI-agent status is pushed in from outside via set_ai_status();
        # default to an idle "ready" state.
        self._ai_text = "AI ready"
        self._ai_busy = False
        self.SetBackgroundColour(COLOR_BG)

        font = wx.Font(11, wx.FONTFAMILY_DEFAULT,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        mono = wx.Font(11, wx.FONTFAMILY_TELETYPE,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        def lbl(text, color=COLOR_INK, f=font):
            t = wx.StaticText(self, label=text)
            t.SetForegroundColour(color)
            t.SetFont(f)
            return t

        # Brand mark on the far left.
        self.brand = lbl("PLC-Cursor", COLOR_ACCENT,
                         wx.Font(11, wx.FONTFAMILY_DEFAULT,
                                 wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        self.sep1 = lbl("·", COLOR_DIM)
        self.project_label = lbl("no project", COLOR_DIM, mono)

        self.sep2 = lbl("·", COLOR_DIM)
        self.runtime_label = lbl("runtime: disconnected", COLOR_DIM, mono)

        self.sep3 = lbl("·", COLOR_DIM)
        self.led = _LED(self, COLOR_STOP)
        self.state_label = lbl("Stopped", COLOR_DIM, mono)

        self.sep4 = lbl("·", COLOR_DIM)
        self.cycle_label = lbl("cycle —", COLOR_DIM, mono)

        self.sep5 = lbl("·", COLOR_DIM)
        self.build_label = lbl("build —", COLOR_DIM, mono)

        # Active editor: which POU is open and in what IEC language.
        self.sep6 = lbl("·", COLOR_DIM)
        self.pou_label = lbl("—", COLOR_DIM, mono)

        # Right-side: live AI-agent status (dot + text) then the product tagline.
        self.ai_led = _LED(self, COLOR_STOP)
        self.ai_label = lbl("AI ready", COLOR_DIM, font)
        self.sep7 = lbl("·", COLOR_DIM)
        self.tagline = lbl("AI-native IEC 61131-3 IDE  ·  ST · LD · FBD",
                           COLOR_DIM, font)

        s = wx.BoxSizer(wx.HORIZONTAL)
        s.AddSpacer(10)
        s.Add(self.brand, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep1, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.project_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep2, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.runtime_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep3, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.led, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        s.Add(self.state_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep4, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.cycle_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep5, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.build_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep6, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.pou_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddStretchSpacer(1)
        s.Add(self.ai_led, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        s.Add(self.ai_label, 0, wx.ALIGN_CENTER_VERTICAL)
        s.AddSpacer(8); s.Add(self.sep7, 0, wx.ALIGN_CENTER_VERTICAL); s.AddSpacer(8)
        s.Add(self.tagline, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)
        self.SetSizer(s)

        self.Bind(wx.EVT_PAINT, self._on_paint)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._refresh, self._timer)
        self._timer.Start(1000)
        self._refresh()

    def _on_paint(self, _e):
        # Bottom border line.
        dc = wx.PaintDC(self)
        size = self.GetClientSize()
        dc.SetPen(wx.Pen(COLOR_BORDER, 1))
        dc.DrawLine(0, size.height - 1, size.width, size.height - 1)

    def _refresh(self, _e=None):
        try:
            self._refresh_impl()
        except Exception:
            # never crash the IDE because the status strip choked.
            pass

    def _refresh_impl(self):
        ctr = self._get_ctr()
        if ctr is None:
            self._set_idle()
            return

        # Project name
        name = "no project"
        try:
            name = ctr.GetProjectName() or "no project"
        except Exception:
            pass
        self.project_label.SetLabel(name)
        self.project_label.SetForegroundColour(COLOR_INK if name != "no project" else COLOR_DIM)

        # Runtime URI
        uri = "disconnected"
        try:
            uri = (ctr.BeremizRoot.getURI_location() or "").strip() or "disconnected"
        except Exception:
            pass
        if uri.upper() == "LOCAL://":
            uri = "LOCAL://  (simulation)"
        self.runtime_label.SetLabel("runtime: " + uri)

        # PLC State
        state = "Stopped"
        led_color = COLOR_STOP
        try:
            ps = getattr(ctr, "previous_plcstate", None)
            if ps:
                state = str(ps)
                if state.lower() in ("started", "running"):
                    led_color = COLOR_RUN
                elif state.lower() == "broken":
                    led_color = COLOR_BROKEN
        except Exception:
            pass
        self.state_label.SetLabel(state)
        self.state_label.SetForegroundColour(
            COLOR_INK if led_color is COLOR_RUN else COLOR_DIM)
        self.led.set_color(led_color)

        # Cycle time — pulled from first task in project config.
        cycle = "—"
        try:
            project = ctr.GetProject()
            if project is not None:
                for cfg in project.getconfigurations():
                    for res in cfg.getresource():
                        for task in res.gettask():
                            interval = task.getinterval()
                            if interval:
                                cycle = str(interval)
                                raise StopIteration
        except StopIteration:
            pass
        except Exception:
            pass
        self.cycle_label.SetLabel("cycle " + cycle)

        # Build status — best-effort guess from buildpath existence.
        build = "—"
        try:
            import os
            bp = ctr._getBuildPath()
            if os.path.exists(os.path.join(bp, "lastbuildPLC.md5")):
                build = "✓ ok"
        except Exception:
            pass
        self.build_label.SetLabel("build " + build)
        self.build_label.SetForegroundColour(
            COLOR_RUN if build == "✓ ok" else COLOR_DIM)

        # Active POU + IEC language from the focused editor tab.
        pou = "—"
        try:
            frame = self._get_frame()
            if frame is not None:
                sel = frame.TabsOpened.GetSelection()
                if sel != -1:
                    window = frame.TabsOpened.GetPage(sel)
                    tagname = window.GetTagName()
                    if tagname:
                        name = tagname.split("::")[-1]
                        lang = None
                        try:
                            lang = frame.Controler.GetEditedElementBodyType(tagname)
                        except Exception:
                            lang = None
                        pou = "%s · %s" % (name, lang) if lang else name
        except Exception:
            pass
        self.pou_label.SetLabel(pou)
        self.pou_label.SetForegroundColour(COLOR_INK if pou != "—" else COLOR_DIM)

        # AI-agent indicator (state pushed in via set_ai_status).
        self.ai_label.SetLabel(self._ai_text)
        if self._ai_busy:
            self.ai_led.set_color(COLOR_ACCENT)
            self.ai_label.SetForegroundColour(COLOR_ACCENT)
        else:
            self.ai_led.set_color(COLOR_RUN)
            self.ai_label.SetForegroundColour(COLOR_DIM)

        self.Layout()

    def set_ai_status(self, text, busy=False):
        """Update the AI-agent indicator. `busy=True` paints it amber
        (agent working); otherwise it shows an idle green 'ready' dot.
        Safe to call from any thread via wx.CallAfter."""
        self._ai_text = text or "AI ready"
        self._ai_busy = bool(busy)
        try:
            self._refresh()
        except Exception:
            pass

    def _set_idle(self):
        self.project_label.SetLabel("no project")
        self.project_label.SetForegroundColour(COLOR_DIM)
        self.runtime_label.SetLabel("runtime: disconnected")
        self.state_label.SetLabel("Stopped")
        self.state_label.SetForegroundColour(COLOR_DIM)
        self.led.set_color(COLOR_STOP)
        self.cycle_label.SetLabel("cycle —")
        self.build_label.SetLabel("build —")
        self.pou_label.SetLabel("—")
        self.pou_label.SetForegroundColour(COLOR_DIM)
        self.ai_label.SetLabel(self._ai_text)
        self.ai_led.set_color(COLOR_ACCENT if self._ai_busy else COLOR_RUN)
        self.Layout()
