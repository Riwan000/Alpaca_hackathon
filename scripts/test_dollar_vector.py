import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import matplotlib.textpath as tp
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path

# Desired dimensions
TARGET_W, TARGET_H = 1024, 1024
CENTER_X, CENTER_Y = 512, 490
DOLLAR_HEIGHT = 420  # Height of dollar sign in SVG

# 1. Get TextPath from Arial Bold
fp = FontProperties(family='Arial', weight='bold')
raw_path = tp.TextPath((0, 0), '$', size=100, prop=fp)

# Bounding box of raw path
verts = raw_path.vertices.copy()
min_x, min_y = verts.min(axis=0)
max_x, max_y = verts.max(axis=0)
raw_w = max_x - min_x
raw_h = max_y - min_y

scale = DOLLAR_HEIGHT / raw_h
dollar_w = raw_w * scale

print(f"Dollar dimensions: width={dollar_w:.1f}, height={DOLLAR_HEIGHT:.1f}")

# Function to transform vertices: scale and center at (CENTER_X, CENTER_Y)
# Note: In matplotlib TextPath, y is positive upwards. In SVG, y is positive downwards.
def transform_point(x, y):
    # Normalize from [min_x, max_x] and [min_y, max_y]
    nx = (x - (min_x + max_x) / 2) * scale + CENTER_X
    ny = -(y - (min_y + max_y) / 2) * scale + CENTER_Y
    return nx, ny

# Generate SVG path d string
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

dollar_svg_path = build_svg_d(raw_path)
print("Dollar SVG path generated successfully, length:", len(dollar_svg_path))
