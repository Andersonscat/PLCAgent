"""toolbar_icons — custom, high-quality vector icons for the IDE toolbar.

Hand-authored Lucide/Feather-style line icons (24×24 viewBox, 2px round
stroke), rasterised via wx.svg at 2× device pixels and tagged HiDPI so they
stay razor-sharp on Retina. Replaces the dated bundled Beremiz PNG glyphs.

Use get_toolbar_icon(name, size, ink_hex) -> wx.Bitmap | None.
"""

import wx

try:
    import wx.svg
    from wx.svg import SVGimage
    _SVG_OK = True
except Exception:
    _SVG_OK = False


# Inner SVG markup per tool (stroke icons unless noted). Names match the
# bitmap keys used by the StatusToolBar groups.
_ICONS = {
    "tool_new":      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "tool_open":     '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "tool_save":     '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M8 3v5h7"/><path d="M8 14h8v6H8z"/>',
    "tool_print":    '<path d="M7 9V3h10v6"/><path d="M7 18H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v7H7z"/>',
    "tool_cut":      '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><line x1="20" y1="4" x2="8.5" y2="15.5"/><line x1="14.5" y1="14.5" x2="20" y2="20"/><line x1="8.5" y1="8.5" x2="12" y2="12"/>',
    "tool_copy":     '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"/>',
    "tool_paste":    '<path d="M15 4h2a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="9" y="2" width="6" height="4" rx="1"/>',
    "tool_delete":   '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "tool_undo":     '<path d="M3 8h10a5 5 0 0 1 0 10H7"/><path d="M6 4 3 8l3 4"/>',
    "tool_redo":     '<path d="M21 8H11a5 5 0 0 0 0 10h6"/><path d="M18 4l3 4-3 4"/>',
    "tool_verify":   '<path d="M21 11.5V12a9 9 0 1 1-5.3-8.2"/><path d="M9 11l3 3 9-9"/>',
    "tool_clean":    '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "tool_ieccode":  '<path d="M16 6l6 6-6 6"/><path d="M8 6l-6 6 6 6"/>',
    "tool_online":   '<path d="M9 13a5 5 0 0 0 7.5.5l3-3A5 5 0 0 0 12.5 3.5L11 5"/><path d="M15 11a5 5 0 0 0-7.5-.5l-3 3A5 5 0 0 0 11.5 20.5L13 19"/>',
    "tool_download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "tool_run":      '<path d="M7 4l13 8-13 8z"/>',           # filled (green)
    "tool_stop":     '<rect x="6" y="6" width="12" height="12" rx="2"/>',  # filled (red)
    "tool_offline":  '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/><line x1="12" y1="2" x2="12" y2="12"/>',
    "tool_generate": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    "tool_upload":   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 8l5-5 5 5"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "tool_debug":    '<rect x="8" y="7" width="8" height="13" rx="4"/><path d="M12 2v5M5 8l3 1M19 8l-3 1M3 14h5M16 14h5M5 20l3-2M19 20l-3-2"/>',
    "select":        '<path d="M5 3l13 8-5.5 1.5L9 19z"/>',   # cursor (filled)
}

_FILLED = {"tool_run", "tool_stop", "select"}
_COLORED = {"tool_run": "#2e9e44", "tool_stop": "#c8392b"}


def has_icon(name):
    return _SVG_OK and name in _ICONS


def get_toolbar_icon(name, size=20, ink_hex="#3A3D45"):
    """Return a crisp 2× wx.Bitmap for `name`, or None if not a custom icon."""
    if not has_icon(name):
        return None
    color = _COLORED.get(name, ink_hex)
    filled = name in _FILLED
    fill = color if filled else "none"
    stroke = "none" if filled else color
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">' + _ICONS[name] + '</svg>'
    )
    try:
        image = SVGimage.CreateFromBytes(svg.encode("utf-8"))
        phys = int(size) * 2
        bmp = image.ConvertToScaledBitmap(wx.Size(phys, phys))
        try:
            bmp.SetScaleFactor(2.0)
        except Exception:
            pass
        return bmp
    except Exception:
        return None
