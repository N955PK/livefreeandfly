"""North America's outline for the coverage map in the About sheet (NA_MAP in index.html): Canada, the USA and
Mexico from Natural Earth's 1:50m countries, in an Albers conic projection, simplified, as SVG paths in a box
1,000 wide. Run it in a folder that holds world-atlas's ``package/countries-50m.json`` (``npm pack world-atlas@2``
and unpack); it writes ``na.json``, whose figures and paths are pasted into the page as NA_MAP."""
import json, math
import numpy as np
T = json.load(open('package/countries-50m.json'))
sx, sy = T['transform']['scale']; tx, ty = T['transform']['translate']
arcs = []
for arc in T['arcs']:
    x = y = 0; pts = []
    for dx, dy in arc:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)
def ring(idx):
    out = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        out += a if not out else a[1:]
    return out
def polys(geom):
    if geom['type'] == 'Polygon': return [[ring(r) for r in geom['arcs']]]
    return [[ring(r) for r in p] for p in geom['arcs']]
P1, P2, L0, F0 = math.radians(40), math.radians(62), math.radians(-100), math.radians(50)
n = (math.sin(P1) + math.sin(P2)) / 2; C = math.cos(P1) ** 2 + 2 * n * math.sin(P1); R0 = math.sqrt(C - 2 * n * math.sin(F0)) / n
def proj(lon, lat):
    r = math.sqrt(C - 2 * n * math.sin(math.radians(lat))) / n; th = n * (math.radians(lon) - L0)
    return r * math.sin(th), -(R0 - r * math.cos(th))
# The frame: the Alaska Peninsula to Newfoundland, the Arctic coast to the Gulf of Mexico.
frame = [proj(-166, 54), proj(-141, 70.5), proj(-52, 47), proj(-80, 24.5), proj(-117, 31), proj(-97, 25.5), proj(-150, 71.5), proj(-60, 60)]
x0, x1 = min(p[0] for p in frame), max(p[0] for p in frame); y0, y1 = min(p[1] for p in frame), max(p[1] for p in frame)
k = 1000 / (x1 - x0); H = round((y1 - y0) * k)
def dp(pts, tol):
    if len(pts) < 3: return pts
    a, b = np.array(pts[0]), np.array(pts[-1]); P = np.array(pts); seg = b - a; L = np.hypot(*seg)
    d = np.hypot(*(P - a).T) if L == 0 else np.abs(seg[0] * (P[:, 1] - a[1]) - seg[1] * (P[:, 0] - a[0])) / L
    i = int(d.argmax())
    if d[i] <= tol: return [pts[0], pts[-1]]
    return dp(pts[:i + 1], tol)[:-1] + dp(pts[i:], tol)
out = {}
for g in T['objects']['countries']['geometries']:
    name = {'124': 'ca', '840': 'us', '484': 'mx'}.get(str(g.get('id')))
    if not name: continue
    d = ''
    for poly in polys(g):
        r = poly[0]
        if all(lon > 0 for lon, lat in r): continue          # the far Aleutians, past the date line
        pts = [((proj(lon, lat)[0] - x0) * k, (proj(lon, lat)[1] - y0) * k) for lon, lat in r if lat > 14]
        if len(pts) < 4: continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if max(xs) < -40 or min(xs) > 1040 or max(ys) < -40 or min(ys) > H + 40: continue
        area = abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))) / 2
        if area < 14: continue                                 # islets too small to see
        s = dp(pts, 0.9)
        if len(s) < 4: continue
        d += 'M' + 'L'.join(f'{x:.0f} {y:.0f}' for x, y in s) + 'Z'
    out[name] = d
json.dump({'w': 1000, 'h': H, 'x0': x0, 'y0': y0, 'k': k, 'n': n, 'C': C, 'R0': R0, 'L0': -100, 'paths': out}, open('na.json', 'w'))
print('H', H, {k_: len(v) for k_, v in out.items()}, 'k', k, 'x0', x0, 'y0', y0, 'n', n, 'C', C, 'R0', R0)
