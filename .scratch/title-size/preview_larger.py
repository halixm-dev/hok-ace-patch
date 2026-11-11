"""Preview larger title sprites without changing shipped art or phone data."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'research'))
import atlas_sprites as atlas
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
names = atlas.mg.ATLAS_LABELS[atlas.SECRET_TITLES]
sizes = atlas.title_sizes()
original_layout = atlas.title_layout

def larger_layout(text, size, max_stretch=atlas.TITLE_MAX_STRETCH):
    return original_layout(text, size, max_stretch, points=32)

atlas.title_layout = larger_layout
enlarged = {}
for name, text in names.items():
    size = tuple(round(v * 1.5) for v in sizes[name])
    enlarged[name] = atlas.title_label(text, size, name in atlas.BEVELLED_TITLES)
    target = OUT / 'drafts32'
    target.mkdir(parents=True, exist_ok=True)
    enlarged[name].save(target / f'{name}.png')

sheet = Image.new('RGB', (1500, 840), '#eee7d7')
draw = ImageDraw.Draw(sheet)
font = ImageFont.truetype(str(atlas.TITLE_FONT), 23)
for x, title in [(15, 'CURRENT: 22 PT'), (515, '32 PT: SAME DISPLAY BOX'), (1015, '32 PT: DISPLAY BOX ALSO 1.5X')]:
    draw.text((x, 12), title, font=font, fill='black')
selected = ['Image_608660137', 'Image_336894947', 'Image_1003624714', 'Image_68423477', 'Image_15320793', 'Image_1758425074']
for row, name in enumerate(selected):
    y = 80 + row * 120
    current = Image.open(ROOT / 'resources' / 'sprites' / atlas.SECRET_TITLES / 'labels' / f'{name}.png').convert('RGBA')
    same = enlarged[name].resize(sizes[name], Image.Resampling.LANCZOS)
    for col, image in enumerate([current, same, enlarged[name]]):
        x = col * 500 + 15
        draw.rectangle((x, y, x + image.width, y + image.height), outline='#998864')
        sheet.paste(image, (x, y), image)
sheet.save(OUT / 'larger-comparison.png')
print(f'All {len(enlarged)} titles fit at 32 pt in 1.5x sprite boxes.')
print(OUT / 'larger-comparison.png')

