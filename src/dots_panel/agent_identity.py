"""Panel-local identity evidence and original, fixed vector portraits.

A portrait is presentation, never proof of a platform identity or live session.
"""
import hashlib

PALETTES = {
    'mint': ('#e7f4ea', '#93c7a3', '#386850'),
    'sky': ('#e9f2fa', '#8bb9d6', '#365f7a'),
    'lavender': ('#f0ebf8', '#b29bd3', '#65517f'),
    'peach': ('#fcEEE3', '#e1af88', '#835b44'),
    'rose': ('#f9eaf0', '#d99bad', '#815169'),
    'teal': ('#e5f3f1', '#86bfb8', '#386c66'),
    'amber': ('#fbf3dd', '#d9b762', '#806629'),
    'slate': ('#eaeef4', '#9baac2', '#4e617c'),
}
MOTIFS = ('leaf', 'orbit', 'comet', 'bloom', 'wave', 'peak')
PORTRAITS = tuple(f'{motif}-{palette}' for motif in MOTIFS for palette in PALETTES)
IDENTITY_SOURCES = ('unknown', 'manual', 'historical')
IDENTITY_VERIFICATIONS = ('unknown', 'observed', 'historical')


def default_portrait(key, palette='mint'):
    # Compatibility fallback is deterministic; storing a selected portrait locks it.
    motif = MOTIFS[int(hashlib.sha256(str(key).encode()).hexdigest()[:8], 16) % len(MOTIFS)]
    return f"{motif}-{palette if palette in PALETTES else 'mint'}"


def available_portrait(db, key, palette='mint'):
    """Pick an unused authored style inside the caller's write transaction.

    The 48-style catalog is finite; after exhaustion style reuse never merges IDs.
    Explicit user-selected styles remain supported separately.
    """
    preferred = default_portrait(key, palette)
    used = {row['portrait'] or default_portrait(row['id'],row['avatar']) for row in db.execute('SELECT id,avatar,portrait FROM agents')}
    candidates = [preferred, *(p for p in PORTRAITS if p.endswith('-'+palette)), *PORTRAITS]
    return next((p for p in candidates if p not in used), preferred)


def identity_label(agent, language='zh'):
    en = language == 'en'
    state = agent.get('identity_verification', 'unknown')
    labels = {'observed': ('人工核验对应关系 · 非永久会话', 'Manually matched · not a permanent session'),
              'historical': ('历史档案 · 当前执行者未核验', 'Historical profile · current executor unverified'),
              'unknown': ('面板档案 · 执行者对应未核验', 'Panel profile · executor match unverified')}
    return labels.get(state, labels['unknown'])[en]


def source_label(agent, language='zh'):
    labels = {'manual': ('人工核验', 'Manual verification'), 'historical': ('历史留存', 'Historical records'), 'unknown': ('来源未核验', 'Source unverified')}
    return labels.get(agent.get('identity_source'), labels['unknown'])[language == 'en']


def portrait_spec(agent):
    """One authored geometry source consumed by native Canvas and Web SVG."""
    key = agent.get('portrait') or default_portrait(agent.get('id', ''), agent.get('avatar', 'mint'))
    if key not in PORTRAITS:
        key = 'leaf-mint'
    motif, palette = key.split('-')
    light, medium, dark = PALETTES[palette]
    shapes = []
    def ellipse(x, y, rx, ry, fill):
        shapes.append({'tag': 'ellipse', 'attrs': {'cx': x, 'cy': y, 'rx': rx, 'ry': ry, 'fill': fill}})
    def line(points, stroke, width=2):
        shapes.append({'tag': 'polyline', 'attrs': {'points': points, 'fill': 'none', 'stroke': stroke, 'stroke-width': width, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}})
    def polygon(points, fill):
        shapes.append({'tag': 'polygon', 'attrs': {'points': points, 'fill': fill}})
    shapes.append({'tag': 'rect', 'attrs': {'x': 1, 'y': 1, 'width': 62, 'height': 62, 'rx': 19, 'fill': light}})
    ellipse(32, 53, 20, 4, medium)
    ellipse(15, 33, 5, 6, medium); ellipse(49, 33, 5, 6, medium)
    shapes.append({'tag': 'rect', 'attrs': {'x': 15, 'y': 18, 'width': 34, 'height': 34, 'rx': 13, 'fill': medium}})
    shapes.append({'tag': 'rect', 'attrs': {'x': 18, 'y': 22, 'width': 28, 'height': 25, 'rx': 10, 'fill': light}})
    if motif == 'leaf':
        line('32,20 32,11', dark); ellipse(27, 10, 7, 3, medium); ellipse(38, 7, 7, 3, dark)
    elif motif == 'orbit':
        ellipse(32, 12, 13, 3, dark); ellipse(43, 9, 3, 3, medium)
    elif motif == 'comet':
        polygon('32,4 35,11 43,12 37,17 38,24 32,20 26,24 27,17 21,12 29,11', dark)
    elif motif == 'bloom':
        for x, y in ((27, 8), (36, 8), (25, 15), (39, 15)):
            ellipse(x, y, 4, 4, medium)
        ellipse(32, 12, 5, 5, dark)
    elif motif == 'wave':
        line('20,15 26,10 32,15 38,10 44,15', dark, 3)
    else:
        polygon('21,18 27,5 33,14 39,5 45,18', dark)
    ellipse(26, 33, 2, 3, dark); ellipse(38, 33, 2, 3, dark)
    ellipse(22, 38, 2.5, 1.4, medium); ellipse(42, 38, 2.5, 1.4, medium)
    line('29,40 32,42 35,40', dark, 1.8)
    return {'key': key, 'viewBox': '0 0 64 64', 'shapes': shapes}


def draw_portrait(canvas, agent, x=0, y=0, size=56):
    """Draw exactly the same fixed primitive geometry as the web SVG."""
    scale = size / 64
    for shape in portrait_spec(agent)['shapes']:
        a = shape['attrs']; tag = shape['tag']
        fill = a.get('fill', 'none'); fill = '' if fill == 'none' else fill
        if tag == 'ellipse':
            canvas.create_oval(x+(a['cx']-a['rx'])*scale, y+(a['cy']-a['ry'])*scale,
                               x+(a['cx']+a['rx'])*scale, y+(a['cy']+a['ry'])*scale, fill=fill, outline='')
        elif tag == 'rect':
            left, top = x+a['x']*scale, y+a['y']*scale
            right, bottom = left+a['width']*scale, top+a['height']*scale
            r = a['rx']*scale
            canvas.create_polygon(left+r,top,right-r,top,right,top,right,top+r,right,bottom-r,right,bottom,right-r,bottom,left+r,bottom,left,bottom,left,bottom-r,left,top+r,left,top,
                                  smooth=True, splinesteps=24, fill=fill, outline='')
        else:
            coords = [float(v) for pair in a['points'].split() for v in pair.split(',')]
            coords = [(x if i % 2 == 0 else y)+v*scale for i,v in enumerate(coords)]
            if tag == 'polygon':
                canvas.create_polygon(*coords, fill=fill, outline='')
            else:
                canvas.create_line(*coords, fill=a['stroke'], width=a['stroke-width']*scale, capstyle='round', joinstyle='round')


def profile_short_ids(agents):
    """Display-only local profile fingerprints; full stored IDs remain join keys."""
    full={a['id']:hashlib.sha256(('panel-profile\0'+a['id']).encode()).hexdigest() for a in agents}
    result={}
    for key,value in full.items():
        length=8
        while length<64 and any(other!=key and digest[:length]==value[:length] for other,digest in full.items()):length+=4
        result[key]=value[:length]
    return result
