from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).with_name('tree.ico')
img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((12, 12, 244, 244), radius=52, fill=(31, 95, 139, 255))
d.line((128, 208, 128, 112), fill=(255, 255, 255, 255), width=14)
d.line((128, 154, 72, 96), fill=(255, 255, 255, 255), width=12)
d.line((128, 134, 184, 86), fill=(255, 255, 255, 255), width=12)
for x, y, r, c in [(128, 90, 28, (240, 161, 58, 255)), (66, 82, 23, (93, 190, 160, 255)), (190, 74, 23, (104, 161, 232, 255))]:
    d.ellipse((x-r, y-r, x+r, y+r), fill=c)
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
print(out)
