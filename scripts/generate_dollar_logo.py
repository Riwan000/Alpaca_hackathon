import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import matplotlib.textpath as tp
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options

TARGET_W, TARGET_H = 1024, 1024
CENTER_X, CENTER_Y = 512, 490
DOLLAR_HEIGHT = 440

# 1. Get exact vector path of Arial Bold '$'
fp = FontProperties(family='Arial', weight='bold')
raw_path = tp.TextPath((0, 0), '$', size=100, prop=fp)

verts = raw_path.vertices.copy()
min_x, min_y = verts.min(axis=0)
max_x, max_y = verts.max(axis=0)
raw_w = max_x - min_x
raw_h = max_y - min_y

scale = DOLLAR_HEIGHT / raw_h
dollar_w = raw_w * scale

def transform_point(x, y):
    nx = (x - (min_x + max_x) / 2) * scale + CENTER_X
    ny = -(y - (min_y + max_y) / 2) * scale + CENTER_Y
    return nx, ny

def build_svg_d(p):
    parts = []
    codes = p.codes
    verts = p.vertices
    i = 0
    while i < len(codes):
        code = codes[i]
        if code == Path.MOVETO:
            x, y = transform_point(verts[i][0], verts[i][1])
            parts.append(f"M {x:.2f} {y:.2f}")
            i += 1
        elif code == Path.LINETO:
            x, y = transform_point(verts[i][0], verts[i][1])
            parts.append(f"L {x:.2f} {y:.2f}")
            i += 1
        elif code == Path.CURVE3:
            x1, y1 = transform_point(verts[i][0], verts[i][1])
            x2, y2 = transform_point(verts[i+1][0], verts[i+1][1])
            parts.append(f"Q {x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f}")
            i += 2
        elif code == Path.CURVE4:
            x1, y1 = transform_point(verts[i][0], verts[i][1])
            x2, y2 = transform_point(verts[i+1][0], verts[i+1][1])
            x3, y3 = transform_point(verts[i+2][0], verts[i+2][1])
            parts.append(f"C {x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f} {x3:.2f} {y3:.2f}")
            i += 3
        elif code == Path.CLOSEPOLY:
            parts.append("Z")
            i += 1
        else:
            i += 1
    return " ".join(parts)

dollar_full_d = build_svg_d(raw_path)

# 2. Rasterize to high-res bitmap to sample exact pixel grid for lower half
mask_img = Image.new('L', (TARGET_W, TARGET_H), 0)
draw = ImageDraw.Draw(mask_img)

font_size = int(DOLLAR_HEIGHT * 0.96)
font = ImageFont.truetype('arialbd.ttf', font_size)

draw.text((CENTER_X, CENTER_Y), "$", fill=255, font=font, anchor='mm')
arr = np.array(mask_img)

def chart_y_at(x):
    return 490.0 - 0.52 * (x - 512.0)

cell_size = 15
gap = 2
rect_size = cell_size - gap

pixel_rects = []
for y in range(0, TARGET_H, cell_size):
    for x in range(0, TARGET_W, cell_size):
        sub = arr[y:y+cell_size, x:x+cell_size]
        if sub.size > 0 and sub.mean() > 55:
            cx_block = x + cell_size / 2
            cy_block = y + cell_size / 2
            
            if cy_block >= chart_y_at(cx_block) - 5:
                dist = cy_block - chart_y_at(cx_block)
                if dist < 25:
                    color = "#FEF08A"
                    opacity = 0.95
                elif dist < 55:
                    color = "#FACC15"
                    opacity = 0.95
                elif dist < 95:
                    color = "#10B981"
                    opacity = 0.95
                elif dist < 140:
                    color = "#0D9488"
                    opacity = 0.9
                else:
                    color = "#059669"
                    opacity = 0.85
                
                pixel_rects.append(f'<rect x="{x+gap/2:.1f}" y="{y+gap/2:.1f}" width="{rect_size:.1f}" height="{rect_size:.1f}" rx="2" fill="{color}" fill-opacity="{opacity:.2f}"/>')

# Floating voxel dissolve particles
scatter_pixels = [
    (615, 520, 10, "#FACC15", 0.5),
    (635, 550, 8, "#EAB308", 0.4),
    (645, 580, 12, "#10B981", 0.35),
    (410, 620, 10, "#0D9488", 0.4),
    (390, 650, 8, "#10B981", 0.3),
    (530, 690, 10, "#059669", 0.4),
    (480, 705, 12, "#10B981", 0.35),
    (580, 660, 9, "#10B981", 0.45),
    (360, 580, 11, "#0D9488", 0.35)
]

for sx, sy, s_size, s_col, s_op in scatter_pixels:
    pixel_rects.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{s_size:.1f}" height="{s_size:.1f}" rx="2" fill="{s_col}" fill-opacity="{s_op:.2f}"/>')

pixel_svg_markup = "\n      ".join(pixel_rects)

# Construct Clean Master SVG for Logo (1024x1024, No Candlesticks)
logo_svg = f"""<svg width="1024" height="1024" viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="bgRadial" cx="0.5" cy="0.5" r="0.75">
      <stop offset="0%" stop-color="#081F16"/>
      <stop offset="45%" stop-color="#04120D"/>
      <stop offset="85%" stop-color="#020805"/>
      <stop offset="100%" stop-color="#010403"/>
    </radialGradient>

    <radialGradient id="shieldGlow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.32"/>
      <stop offset="50%" stop-color="#0D9488" stop-opacity="0.1"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="goldCoreGlow" cx="0.5" cy="0.4" r="0.38">
      <stop offset="0%" stop-color="#FACC15" stop-opacity="0.35"/>
      <stop offset="60%" stop-color="#CA8A04" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>

    <linearGradient id="dollarUpperGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="25%" stop-color="#FEF08A"/>
      <stop offset="60%" stop-color="#FACC15"/>
      <stop offset="90%" stop-color="#EAB308"/>
      <stop offset="100%" stop-color="#CA8A04"/>
    </linearGradient>

    <linearGradient id="hexGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FACC15"/>
      <stop offset="50%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#0D9488"/>
    </linearGradient>

    <linearGradient id="shieldFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.18"/>
      <stop offset="65%" stop-color="#064E3B" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#020805" stop-opacity="0.4"/>
    </linearGradient>

    <linearGradient id="chartGrad" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#EF4444" stop-opacity="0.6"/>
      <stop offset="30%" stop-color="#10B981"/>
      <stop offset="70%" stop-color="#34D399"/>
      <stop offset="100%" stop-color="#FACC15"/>
    </linearGradient>

    <filter id="neonGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="14" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <pattern id="radarGrid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#10B981" stroke-width="0.6" stroke-opacity="0.12"/>
      <circle cx="48" cy="48" r="0.9" fill="#FACC15" fill-opacity="0.2"/>
    </pattern>

    <clipPath id="upperChartClip">
      <polygon points="0,0 1024,0 1024,210 660,390 512,490 380,560 0,710 0,0"/>
    </clipPath>
  </defs>

  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@700;800&amp;display=swap');
    .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
  </style>

  <!-- Background Base -->
  <rect width="1024" height="1024" fill="url(#bgRadial)"/>
  <rect width="1024" height="1024" fill="url(#radarGrid)"/>
  <circle cx="512" cy="512" r="450" fill="url(#shieldGlow)"/>
  <circle cx="512" cy="480" r="320" fill="url(#goldCoreGlow)"/>

  <!-- Concentric Orbital Radar Rings -->
  <circle cx="512" cy="512" r="380" fill="none" stroke="#10B981" stroke-width="1.2" stroke-opacity="0.15" stroke-dasharray="8,8"/>
  <circle cx="512" cy="512" r="300" fill="none" stroke="#FACC15" stroke-width="1.2" stroke-opacity="0.2"/>
  <circle cx="512" cy="512" r="220" fill="none" stroke="#10B981" stroke-width="0.8" stroke-opacity="0.15"/>

  <!-- Central Hex Shield Frame -->
  <g id="shield-container">
    <polygon points="512,180 780,335 780,645 512,800 244,645 244,335" 
             fill="url(#shieldFill)" stroke="url(#hexGrad)" stroke-width="4.5" filter="url(#neonGlow)"/>

    <polygon points="512,215 745,350 745,625 512,760 279,625 279,350" 
             fill="none" stroke="#10B981" stroke-width="1.5" stroke-opacity="0.5" stroke-dasharray="6,4"/>

    <!-- Corner Anchor Nodes -->
    <circle cx="512" cy="180" r="5" fill="#FACC15" filter="url(#subtleGlow)"/>
    <circle cx="780" cy="335" r="5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="780" cy="645" r="5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="512" cy="800" r="5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="244" cy="645" r="5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="244" cy="335" r="5" fill="#FACC15" filter="url(#subtleGlow)"/>
  </g>

  <!-- ==================== THE DOLLAR SYMBOL ==================== -->
  
  <!-- 1. LOWER HALF: PIXELATED VOXELS -->
  <g id="dollar-pixelated-lower">
    {pixel_svg_markup}
  </g>

  <!-- 2. UPPER HALF: PERFECT SMOOTH METALLIC VECTOR GLYPH -->
  <g id="dollar-clear-upper" clip-path="url(#upperChartClip)">
    <path d="{dollar_full_d}" fill="url(#dollarUpperGrad)" filter="url(#subtleGlow)"/>
    <path d="{dollar_full_d}" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-opacity="0.6"/>
  </g>

  <!-- ==================== DIAGONAL STOCK CHART LINE (CLEAN, NO CANDLESTICKS) ==================== -->
  <g id="diagonal-stock-chart">
    <polygon points="100,710 380,620 512,490 660,390 924,210 924,760 100,760" 
             fill="url(#chartGrad)" fill-opacity="0.04"/>

    <line x1="100" y1="710" x2="380" y2="710" stroke="#10B981" stroke-width="2" stroke-dasharray="6,4" stroke-opacity="0.6"/>
    <circle cx="380" cy="710" r="4.5" fill="#10B981" filter="url(#subtleGlow)"/>
    <text x="120" y="698" fill="#10B981" class="font-mono" font-size="12" font-weight="700" letter-spacing="1">HEDGE FLOOR</text>

    <!-- Main Diagonal Stock Trajectory Line -->
    <path d="M 100 710 
             C 240 700, 360 630, 470 530 
             C 512 490, 560 450, 640 400 
             C 730 340, 810 280, 924 210" 
          fill="none" stroke="url(#chartGrad)" stroke-width="6.5" stroke-linecap="round" filter="url(#neonGlow)"/>

    <path d="M 100 710 
             C 240 700, 360 630, 470 530 
             C 512 490, 560 450, 640 400 
             C 730 340, 810 280, 924 210" 
          fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" opacity="0.9"/>

    <!-- Trajectory Nodes -->
    <circle cx="100" cy="710" r="6" fill="#EF4444" filter="url(#subtleGlow)"/>
    <circle cx="470" cy="530" r="7" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="470" cy="530" r="13" fill="none" stroke="#10B981" stroke-width="1.5" stroke-opacity="0.6"/>

    <circle cx="512" cy="490" r="8" fill="#FACC15" filter="url(#neonGlow)"/>
    <circle cx="512" cy="490" r="16" fill="none" stroke="#FACC15" stroke-width="1.8" stroke-opacity="0.8"/>

    <circle cx="924" cy="210" r="9" fill="#FACC15" filter="url(#neonGlow)"/>
    <circle cx="924" cy="210" r="18" fill="none" stroke="#FACC15" stroke-width="2" stroke-opacity="0.8" stroke-dasharray="4,4"/>
  </g>

  <!-- Logo Typography -->
  <g transform="translate(512, 895)">
    <text x="0" y="0" fill="url(#dollarUpperGrad)" class="font-mono" font-size="28" font-weight="800" letter-spacing="8" text-anchor="middle">AEGIS</text>
    <text x="0" y="26" fill="#10B981" class="font-mono" font-size="12" font-weight="700" letter-spacing="3" text-anchor="middle">AUTONOMOUS PORTFOLIO DEFENSE</text>
  </g>
</svg>"""

with open("assets/logo.svg", "w", encoding="utf-8") as f:
    f.write(logo_svg)

print("Saved clean assets/logo.svg")

# 16:9 Cover Banner:
# Center shield slightly adjusted to (960, 380) for balanced composition
CENTER_COVER_Y = 380
cover_scale = 0.72

def transform_cover_point(x, y):
    nx = (x - (min_x + max_x) / 2) * (scale * cover_scale) + 960
    ny = -(y - (min_y + max_y) / 2) * (scale * cover_scale) + CENTER_COVER_Y
    return nx, ny

def build_cover_svg_d(p):
    parts = []
    codes = p.codes
    verts = p.vertices
    i = 0
    while i < len(codes):
        code = codes[i]
        if code == Path.MOVETO:
            x, y = transform_cover_point(verts[i][0], verts[i][1])
            parts.append(f"M {x:.2f} {y:.2f}")
            i += 1
        elif code == Path.LINETO:
            x, y = transform_cover_point(verts[i][0], verts[i][1])
            parts.append(f"L {x:.2f} {y:.2f}")
            i += 1
        elif code == Path.CURVE3:
            x1, y1 = transform_cover_point(verts[i][0], verts[i][1])
            x2, y2 = transform_cover_point(verts[i+1][0], verts[i+1][1])
            parts.append(f"Q {x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f}")
            i += 2
        elif code == Path.CURVE4:
            x1, y1 = transform_cover_point(verts[i][0], verts[i][1])
            x2, y2 = transform_cover_point(verts[i+1][0], verts[i+1][1])
            x3, y3 = transform_cover_point(verts[i+2][0], verts[i+2][1])
            parts.append(f"C {x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f} {x3:.2f} {y3:.2f}")
            i += 3
        elif code == Path.CLOSEPOLY:
            parts.append("Z")
            i += 1
        else:
            i += 1
    return " ".join(parts)

cover_dollar_full_d = build_cover_svg_d(raw_path)

cover_cell = cell_size * cover_scale
cover_rect_size = rect_size * cover_scale
cover_pixels = []
for y in range(0, TARGET_H, cell_size):
    for x in range(0, TARGET_W, cell_size):
        sub = arr[y:y+cell_size, x:x+cell_size]
        if sub.size > 0 and sub.mean() > 55:
            cx_block = x + cell_size / 2
            cy_block = y + cell_size / 2
            if cy_block >= chart_y_at(cx_block) - 5:
                dist = cy_block - chart_y_at(cx_block)
                if dist < 25:
                    color = "#FEF08A"
                    opacity = 0.95
                elif dist < 55:
                    color = "#FACC15"
                    opacity = 0.95
                elif dist < 95:
                    color = "#10B981"
                    opacity = 0.95
                elif dist < 140:
                    color = "#0D9488"
                    opacity = 0.9
                else:
                    color = "#059669"
                    opacity = 0.85
                
                cov_x = (x + gap/2 - CENTER_X) * cover_scale + 960
                cov_y = (y + gap/2 - CENTER_Y) * cover_scale + CENTER_COVER_Y
                cover_pixels.append(f'<rect x="{cov_x:.1f}" y="{cov_y:.1f}" width="{cover_rect_size:.1f}" height="{cover_rect_size:.1f}" rx="1.5" fill="{color}" fill-opacity="{opacity:.2f}"/>')

cover_pixel_markup = "\n      ".join(cover_pixels)

# Clean 16:9 Cover SVG (NO top pill, NO bottom 3 pills, NO candlesticks)
cover_svg = f"""<svg width="1920" height="1080" viewBox="0 0 1920 1080" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1920" y2="1080" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#020704"/>
      <stop offset="35%" stop-color="#05150E"/>
      <stop offset="75%" stop-color="#071A12"/>
      <stop offset="100%" stop-color="#020604"/>
    </linearGradient>

    <radialGradient id="centerGlow" cx="0.5" cy="0.45" r="0.55">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.25"/>
      <stop offset="45%" stop-color="#0D9488" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="goldAmbient" cx="0.5" cy="0.4" r="0.38">
      <stop offset="0%" stop-color="#FACC15" stop-opacity="0.3"/>
      <stop offset="55%" stop-color="#CA8A04" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>

    <linearGradient id="titleGoldGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="30%" stop-color="#FEF08A"/>
      <stop offset="70%" stop-color="#FACC15"/>
      <stop offset="100%" stop-color="#EAB308"/>
    </linearGradient>

    <linearGradient id="dollarUpperGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="25%" stop-color="#FEF08A"/>
      <stop offset="60%" stop-color="#FACC15"/>
      <stop offset="90%" stop-color="#EAB308"/>
      <stop offset="100%" stop-color="#CA8A04"/>
    </linearGradient>

    <linearGradient id="shieldBorderGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FACC15"/>
      <stop offset="45%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#0D9488"/>
    </linearGradient>

    <linearGradient id="shieldFillGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.16"/>
      <stop offset="60%" stop-color="#064E3B" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#020805" stop-opacity="0.35"/>
    </linearGradient>

    <linearGradient id="chartGrad" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#EF4444" stop-opacity="0.5"/>
      <stop offset="30%" stop-color="#10B981"/>
      <stop offset="70%" stop-color="#34D399"/>
      <stop offset="100%" stop-color="#FACC15"/>
    </linearGradient>

    <filter id="heroGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="16" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <pattern id="cleanGrid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#10B981" stroke-width="0.7" stroke-opacity="0.12"/>
      <circle cx="60" cy="60" r="1" fill="#FACC15" fill-opacity="0.25"/>
    </pattern>

    <clipPath id="coverUpperClip">
      <polygon points="0,0 1920,0 1920,180 1260,310 960,380 860,430 0,580 0,0"/>
    </clipPath>
  </defs>

  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&amp;family=Playfair+Display:wght@700;800;900&amp;family=Plus+Jakarta+Sans:wght@400;500;600;700;800&amp;display=swap');
    .font-serif {{ font-family: 'Playfair Display', Georgia, serif; }}
    .font-sans {{ font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif; }}
    .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
  </style>

  <!-- Background Base -->
  <rect width="1920" height="1080" fill="url(#bgGrad)"/>
  <rect width="1920" height="1080" fill="url(#cleanGrid)"/>
  <rect width="1920" height="1080" fill="url(#centerGlow)"/>
  <rect width="1920" height="1080" fill="url(#goldAmbient)"/>
  <rect x="0" y="0" width="1920" height="3" fill="url(#shieldBorderGrad)"/>

  <!-- Center Hero: Hex Shield + Dollar + Diagonal Chart -->
  <g transform="translate(0, 0)">
    <!-- Concentric Rings -->
    <circle cx="960" cy="380" r="240" fill="none" stroke="#10B981" stroke-width="1" stroke-opacity="0.12" stroke-dasharray="8,8"/>
    <circle cx="960" cy="380" r="190" fill="none" stroke="#FACC15" stroke-width="1.2" stroke-opacity="0.18"/>

    <!-- Aegis Hex Shield -->
    <polygon points="960,225 1150,305 1150,460 960,540 770,460 770,305" 
             fill="url(#shieldFillGrad)" stroke="url(#shieldBorderGrad)" stroke-width="3" filter="url(#heroGlow)"/>
    
    <polygon points="960,250 1125,320 1125,445 960,515 795,445 795,320" 
             fill="none" stroke="#10B981" stroke-width="1.2" stroke-opacity="0.4" stroke-dasharray="4,4"/>

    <!-- Corner Nodes -->
    <circle cx="960" cy="225" r="4.5" fill="#FACC15" filter="url(#subtleGlow)"/>
    <circle cx="1150" cy="305" r="4.5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="1150" cy="460" r="4.5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="960" cy="540" r="4.5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="770" cy="460" r="4.5" fill="#10B981" filter="url(#subtleGlow)"/>
    <circle cx="770" cy="305" r="4.5" fill="#FACC15" filter="url(#subtleGlow)"/>

    <!-- Dollar Lower Half: Pixelated Voxels -->
    <g id="cover-dollar-pixels">
      {cover_pixel_markup}
    </g>

    <!-- Dollar Upper Half: Smooth Clear Vector -->
    <g id="cover-dollar-clear" clip-path="url(#coverUpperClip)">
      <path d="{cover_dollar_full_d}" fill="url(#dollarUpperGrad)" filter="url(#subtleGlow)"/>
      <path d="{cover_dollar_full_d}" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-opacity="0.6"/>
    </g>

    <!-- Diagonal Chart Overlay (Smooth, NO Candlesticks) -->
    <g id="cover-chart">
      <!-- Trajectory Glow -->
      <path d="M 700 510 
               C 800 500, 870 455, 940 395 
               C 975 360, 1010 325, 1060 295 
               C 1120 260, 1180 230, 1240 210" 
            fill="none" stroke="url(#chartGrad)" stroke-width="5" stroke-linecap="round" filter="url(#heroGlow)"/>

      <path d="M 700 510 
               C 800 500, 870 455, 940 395 
               C 975 360, 1010 325, 1060 295 
               C 1120 260, 1180 230, 1240 210" 
            fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" opacity="0.9"/>

      <!-- Floor Support Line -->
      <line x1="720" y1="510" x2="860" y2="510" stroke="#10B981" stroke-width="1.8" stroke-dasharray="4,4"/>
      <circle cx="860" cy="510" r="3.5" fill="#10B981"/>

      <!-- Trajectory Nodes -->
      <circle cx="700" cy="510" r="5" fill="#EF4444" filter="url(#subtleGlow)"/>
      <circle cx="940" cy="395" r="5.5" fill="#10B981" filter="url(#subtleGlow)"/>
      <circle cx="960" cy="375" r="6.5" fill="#FACC15" filter="url(#subtleGlow)"/>
      <circle cx="1240" cy="210" r="7.5" fill="#FACC15" filter="url(#heroGlow)"/>
      <circle cx="1240" cy="210" r="15" fill="none" stroke="#FACC15" stroke-width="1.5" stroke-opacity="0.7" stroke-dasharray="3,3"/>
    </g>
  </g>

  <!-- Typography: Centered, Elegant, Uncluttered -->
  <g transform="translate(960, 700)">
    <text x="0" y="40" fill="url(#titleGoldGrad)" class="font-serif" font-size="82" font-weight="900" letter-spacing="-1" text-anchor="middle">AEGIS</text>
    <text x="0" y="98" fill="#34D399" class="font-sans" font-size="28" font-weight="700" letter-spacing="0.5" text-anchor="middle">Autonomous Adaptive Portfolio Hedge Agent</text>
    <text x="0" y="142" fill="#9CA3AF" class="font-sans" font-size="18" font-weight="400" text-anchor="middle">
      Intelligent closed-loop portfolio defense &amp; option collars for institutional wealth.
    </text>
  </g>

  <!-- Minimal Footer -->
  <g transform="translate(960, 1015)">
    <line x1="-700" y1="0" x2="700" y2="0" stroke="#10B981" stroke-width="1" stroke-opacity="0.2"/>
    <text x="0" y="32" fill="#6B7280" class="font-mono" font-size="12" letter-spacing="2" text-anchor="middle">
      PYTHON 3.11 • FASTAPI • POSTGRESQL • LANGGRAPH • ALPACA TRADING API
    </text>
  </g>
</svg>"""

with open("assets/cover_image.svg", "w", encoding="utf-8") as f:
    f.write(cover_svg)

print("Saved clean assets/cover_image.svg")

# Render PNGs using headless Edge
options = Options()
options.add_argument('--headless')
options.add_argument('--hide-scrollbars')

driver = webdriver.Edge(options=options)

# 1. Render Logo (1024x1024)
driver.set_window_size(1024, 1024)
logo_path = os.path.abspath('assets/logo.svg')
driver.get(f'file:///{logo_path}')
driver.save_screenshot('assets/logo.png')
driver.save_screenshot('assets/logo_icon.png')

# 2. Render Cover Image (1920x1080)
driver.set_window_size(1920, 1080)
cover_path = os.path.abspath('assets/cover_image.svg')
driver.get(f'file:///{cover_path}')
driver.save_screenshot('assets/cover_image.png')

# Artifact copies
artifact_dir = r"C:\Users\LEGION\.gemini\antigravity\brain\b7f5ee5f-1cb3-4286-90ef-50bf09d35e04"
os.makedirs(artifact_dir, exist_ok=True)
driver.save_screenshot(os.path.join(artifact_dir, "cover_image.png"))
with open(os.path.join(artifact_dir, "cover_image.svg"), "w", encoding="utf-8") as f:
    f.write(cover_svg)

driver.set_window_size(1024, 1024)
driver.get(f'file:///{logo_path}')
driver.save_screenshot(os.path.join(artifact_dir, "logo.png"))
with open(os.path.join(artifact_dir, "logo.svg"), "w", encoding="utf-8") as f:
    f.write(logo_svg)

driver.quit()
print("Clean minimal Logo and 16:9 Cover rendered and saved successfully!")
