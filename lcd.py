from smbus2 import SMBus
import time
from PIL import Image, ImageDraw, ImageFont

# OLED parameters
I2C_BUS = 4        # Using I2C4
OLED_ADDR = 0x3C   # Typical SSD1306 address

WIDTH =140
HEIGHT = 80

bus = SMBus(I2C_BUS)


def command(cmd):
    bus.write_byte_data(OLED_ADDR, 0x00, cmd)


def data(data):
    bus.write_byte_data(OLED_ADDR, 0x40, data)


def init_display():
    command(0xAE)  # Display OFF
    command(0x20)  # Set Memory Addressing Mode
    command(0x00)  # Horizontal addressing mode
    command(0xB0)  # Page start
    command(0xC8)
    command(0x00)
    command(0x10)
    command(0x40)
    command(0x81)
    command(0xFF)
    command(0xA1)
    command(0xA6)
    command(0xA8)
    command(0x3F)
    command(0xA4)
    command(0xD3)
    command(0x00)
    command(0xD5)
    command(0xF0)
    command(0xD9)
    command(0x22)
    command(0xDA)
    command(0x12)
    command(0xDB)
    command(0x20)
    command(0x8D)
    command(0x14)
    command(0xAF)  # Display ON


def clear_display():
    for page in range(8):
        command(0xB0 + page)
        command(0x00)
        command(0x10)
        for _ in range(128):
            data(0x00)


def display_image(image):
    pixels = image.load()

    for page in range(8):
        command(0xB0 + page)
        command(0x00)
        command(0x10)

        for x in range(WIDTH):
            byte = 0
            for bit in range(8):
                y = page * 8 + bit
                if pixels[x, y] != 0:
                    byte |= (1 << bit)
            data(byte)


# Initialize display
init_display()
clear_display()

# Create image
image = Image.new("1", (WIDTH, HEIGHT))
draw = ImageDraw.Draw(image)

#font = ImageFont.load_default()

font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoMono-Regular.ttf",20)

draw.text((10,20), "Fuck you", font=font, fill=255)

# Send image to OLED
display_image(image)

time.sleep(15)
clear_display()
