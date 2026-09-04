import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# 1. Rasterize font glyph to find exact shape and pixel coordinates
W, H = 500, 500
img = Image.new('L', (W, H), 0)
draw = ImageDraw.Draw(img)
font_size = 360
font = ImageFont.truetype('arialbd.ttf', font_size)

# Center of canvas
cx, cy = W // 2, H // 2
draw.text((cx, cy), "$", fill=255, font=font, anchor='mm')

arr = np.array(img)
bbox = img.getbbox()
print("BBox:", bbox)
print("Glyph dimensions:", bbox[2] - bbox[0], bbox[3] - bbox[1])
