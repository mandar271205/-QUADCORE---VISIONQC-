"""Render the app's simple eye mark into the missing Expo configuration assets."""
from pathlib import Path
from PIL import Image, ImageDraw

ASSETS=Path(__file__).resolve().parents[1]/'assets'
ASSETS.mkdir(exist_ok=True)
for name,size in [('icon',1024),('adaptive-icon',1024),('splash',1024)]:
    image=Image.new('RGB',(size,size),'#0f1117')
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((192,192,832,832),radius=140,fill='#5a83ff')
    draw.ellipse((300,380,724,644),outline='white',width=30)
    draw.ellipse((438,438,586,586),outline='white',width=25)
    draw.ellipse((490,490,534,534),fill='white')
    image.save(ASSETS/f'{name}.png')
