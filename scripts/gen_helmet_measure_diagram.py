import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Ellipse, Polygon
import numpy as np
import os

os.makedirs('out/preview', exist_ok=True)

fig = plt.figure(figsize=(16, 10))
fig.patch.set_facecolor('#0d1117')

ax1 = fig.add_axes([0.02, 0.10, 0.44, 0.80])
ax2 = fig.add_axes([0.52, 0.10, 0.44, 0.80])

for ax in (ax1, ax2):
    ax.set_facecolor('#0d1117')
    ax.axis('off')

# ───── FRONT VIEW ─────
ax1.set_xlim(-150, 150)
ax1.set_ylim(-20, 240)
ax1.set_aspect('equal')

skull = Ellipse((0, 130), width=160, height=155, color='#d4b896', ec='#8B6914', lw=2, zorder=2)
ax1.add_patch(skull)
face_fill = mpatches.FancyBboxPatch((-57, 10), 114, 120,
    boxstyle="round,pad=2", color='#d4b896', ec='#8B6914', lw=2, zorder=3)
ax1.add_patch(face_fill)
skull2 = Ellipse((0, 130), width=160, height=155, color='#d4b896', ec='#8B6914', lw=2, zorder=4)
ax1.add_patch(skull2)
chin = Ellipse((0, 12), width=108, height=38, color='#d4b896', ec='#8B6914', lw=2, zorder=5)
ax1.add_patch(chin)
for sx in (-83, 83):
    ax1.add_patch(Ellipse((sx, 102), width=18, height=32, color='#d4b896', ec='#8B6914', lw=2, zorder=3))
for ex in (-28, 28):
    ax1.add_patch(Ellipse((ex, 118), width=26, height=14, color='#4a3220', zorder=6))
ax1.add_patch(Ellipse((0, 88), width=18, height=24, color='#c4a882', ec='#8B6914', lw=1, zorder=6))
ax1.add_patch(Ellipse((0, 58), width=38, height=13, color='#7a3020', zorder=6))
ax1.plot([-42, -14], [130, 130], color='#3d2b1f', lw=3, zorder=7)
ax1.plot([14, 42], [130, 130], color='#3d2b1f', lw=3, zorder=7)

# A: Head Width
ax1.annotate('', xy=(83, 160), xytext=(-83, 160),
    arrowprops=dict(arrowstyle='<->', color='#00ff88', lw=2.5), zorder=10)
ax1.text(0, 168, 'A  HEAD WIDTH', ha='center', color='#00ff88', fontsize=10, fontweight='bold')

# B: Head Height
ax1.annotate('', xy=(120, 210), xytext=(120, 0),
    arrowprops=dict(arrowstyle='<->', color='#ffd700', lw=2.5), zorder=10)
ax1.text(123, 105, 'B\nHEIGHT\nchin to crown', ha='left', va='center',
    color='#ffd700', fontsize=9, fontweight='bold')

# C: Face Width
ax1.annotate('', xy=(58, 72), xytext=(-58, 72),
    arrowprops=dict(arrowstyle='<->', color='#ff6b6b', lw=2.5), zorder=10)
ax1.text(0, 63, 'C  FACE WIDTH', ha='center', color='#ff6b6b', fontsize=10, fontweight='bold')

# D: Face Height
ax1.annotate('', xy=(-118, 132), xytext=(-118, 0),
    arrowprops=dict(arrowstyle='<->', color='#a78bfa', lw=2.5), zorder=10)
ax1.text(-122, 66, 'D\nFACE HEIGHT\nchin to brow', ha='right', va='center',
    color='#a78bfa', fontsize=9, fontweight='bold')

# E: Circumference dashed line
circ = Ellipse((0, 115), width=185, height=60, fill=False,
    ec='#00ccff', lw=2.5, linestyle='--', zorder=9)
ax1.add_patch(circ)
ax1.text(0, 148, 'E  CIRCUMFERENCE  (tape at this level)',
    ha='center', color='#00ccff', fontsize=9, fontweight='bold',
    bbox=dict(boxstyle='round,pad=0.3', facecolor='#0d1117', alpha=0.85))

ax1.set_title('FRONT VIEW', color='white', fontsize=13, fontweight='bold', pad=8)

# ───── SIDE PROFILE VIEW ─────
ax2.set_xlim(-30, 210)
ax2.set_ylim(-20, 240)
ax2.set_aspect('equal')

px = np.array([70, 55, 38, 22, 10,  5,  8, 20, 45, 80, 115, 128, 130, 125, 120, 118, 125, 128, 118, 95, 70])
py = np.array([ 0, -5,  2, 20, 48, 80,115,155,195,210, 205, 185, 160, 135, 110,  85,  62,  40,  20,   8,  0])
head_prof = Polygon(np.column_stack([px, py]), closed=True,
    color='#d4b896', ec='#8B6914', lw=2, zorder=2)
ax2.add_patch(head_prof)
ax2.add_patch(Ellipse((22, 105), width=16, height=28, color='#d4b896', ec='#8B6914', lw=2, zorder=3))
ax2.add_patch(Ellipse((108, 128), width=20, height=12, color='#4a3220', zorder=4))

# F: Head Depth
ax2.annotate('', xy=(130, 215), xytext=(8, 215),
    arrowprops=dict(arrowstyle='<->', color='#00ff88', lw=2.5), zorder=10)
ax2.text(69, 224, 'F  HEAD DEPTH  (forehead to back of skull)',
    ha='center', color='#00ff88', fontsize=10, fontweight='bold')

# B: Height (side view)
ax2.annotate('', xy=(160, 210), xytext=(160, 0),
    arrowprops=dict(arrowstyle='<->', color='#ffd700', lw=2.5), zorder=10)
ax2.text(163, 105, 'B\nHEIGHT', ha='left', va='center',
    color='#ffd700', fontsize=9, fontweight='bold')

# G: Chin to ear
ax2.annotate('', xy=(185, 105), xytext=(185, 0),
    arrowprops=dict(arrowstyle='<->', color='#ff9f43', lw=2.5), zorder=10)
ax2.text(188, 52, 'G\nCHIN\nTO EAR', ha='left', va='center',
    color='#ff9f43', fontsize=9, fontweight='bold')

ax2.set_title('SIDE PROFILE VIEW', color='white', fontsize=13, fontweight='bold', pad=8)

# ───── LEGEND ─────
legend_data = [
    ('A', 'Head Width — widest point, ear to ear (outside)', '#00ff88'),
    ('B', 'Head Height — bottom of chin to top of crown', '#ffd700'),
    ('C', 'Face Width — cheekbone to cheekbone', '#ff6b6b'),
    ('D', 'Face Height — chin to middle of brow', '#a78bfa'),
    ('E', 'Circumference — tape ~1 inch above eyebrows', '#00ccff'),
    ('F', 'Head Depth — forehead to back of skull', '#00ff88'),
    ('G', 'Chin to Ear — chin bottom to ear canal level', '#ff9f43'),
]
for i, (letter, desc, color) in enumerate(legend_data):
    col = i % 2
    row = i // 2
    fig.text(0.04 + col * 0.49, 0.075 - row * 0.024,
        '  {}  {}'.format(letter, desc), color=color, fontsize=8.5,
        bbox=dict(boxstyle='round,pad=0.2', facecolor='#161b22', alpha=0.9))

fig.text(0.5, 0.97, 'Snake Eyes Helmet — Head Measurement Guide',
    ha='center', va='top', color='white', fontsize=17, fontweight='bold')
fig.text(0.5, 0.022,
    'Use a flexible tape measure  |  All measurements in mm  |  Have a friend help for accuracy',
    ha='center', color='#666666', fontsize=9)

plt.savefig('out/preview/helmet_measurements.png', dpi=150,
    bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()
print("OK")
