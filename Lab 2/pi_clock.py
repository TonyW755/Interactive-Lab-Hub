import time
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789


# -----------------------------
# Display setup
# -----------------------------

cs_pin = digitalio.DigitalInOut(board.D5)
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = None

BAUDRATE = 64000000

spi = board.SPI()

disp = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)


# -----------------------------
# Create image
# -----------------------------

height = disp.width
width = disp.height

image = Image.new("RGB", (width, height))
rotation = 90

draw = ImageDraw.Draw(image)

font = ImageFont.truetype(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    18
)


# -----------------------------
# Turn on backlight
# -----------------------------

backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True


# -----------------------------
# Draw daytime sun
# -----------------------------

def draw_sun(draw, center_x, center_y, radius):

    # Sun body
    draw.ellipse(
        (
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius
        ),
        fill="yellow"
    )

    # Rays
    draw.line(
        (center_x, center_y - radius - 10,
         center_x, center_y - radius),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x, center_y + radius,
         center_x, center_y + radius + 10),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x - radius - 10, center_y,
         center_x - radius, center_y),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x + radius, center_y,
         center_x + radius + 10, center_y),
        fill="yellow",
        width=3
    )

    # Diagonal rays
    draw.line(
        (center_x - radius - 7, center_y - radius - 7,
         center_x - radius, center_y - radius),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x + radius, center_y - radius,
         center_x + radius + 7, center_y - radius - 7),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x - radius - 7, center_y + radius + 7,
         center_x - radius, center_y + radius),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x + radius, center_y + radius,
         center_x + radius + 7, center_y + radius + 7),
        fill="yellow",
        width=3
    )

    # Eyes
    draw.ellipse(
        (
            center_x - 9,
            center_y - 7,
            center_x - 4,
            center_y - 2
        ),
        fill="black"
    )

    draw.ellipse(
        (
            center_x + 4,
            center_y - 7,
            center_x + 9,
            center_y - 2
        ),
        fill="black"
    )

    # Smile
    draw.arc(
        (
            center_x - 10,
            center_y - 2,
            center_x + 10,
            center_y + 12
        ),
        0,
        180,
        fill="black",
        width=2
    )


# -----------------------------
# Draw sunrise / sunset
# -----------------------------

def draw_horizon_sun(draw, center_x, horizon_y, radius):

    # Horizon line
    draw.line(
        (20, horizon_y, width - 20, horizon_y),
        fill="orange",
        width=3
    )

    # Half sun
    draw.pieslice(
        (
            center_x - radius,
            horizon_y - radius,
            center_x + radius,
            horizon_y + radius
        ),
        180,
        360,
        fill="orange"
    )

    # Rays
    draw.line(
        (center_x, horizon_y - radius - 10,
         center_x, horizon_y - radius),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x - radius - 10, horizon_y - 10,
         center_x - radius, horizon_y - 5),
        fill="yellow",
        width=3
    )

    draw.line(
        (center_x + radius, horizon_y - 5,
         center_x + radius + 10, horizon_y - 10),
        fill="yellow",
        width=3
    )


# -----------------------------
# Main loop
# -----------------------------

while True:

    # Clear screen
    draw.rectangle(
        (0, 0, width, height),
        fill=(0, 0, 0)
    )

    # Get current time
    current_date = time.strftime("%m/%d/%Y")
    current_time = time.strftime("%H:%M:%S")

    hour = int(time.strftime("%H"))
    minute = int(time.strftime("%M"))

    # Convert current time into minutes
    current_minutes = hour * 60 + minute

    # Sunrise = 5:30 AM
    sunrise = 5 * 60 + 30

    # Sunset = 7:00 PM
    sunset = 19 * 60


    # -----------------------------
    # Sunrise: 5:30 AM - 6:00 AM
    # -----------------------------

    if sunrise <= current_minutes < 6 * 60:

        draw.text(
            (75, 5),
            "SUNRISE",
            font=font,
            fill="orange"
        )

        draw_horizon_sun(
            draw,
            width // 2,
            75,
            25
        )


    # -----------------------------
    # Daytime: 6:00 AM - 7:00 PM
    # -----------------------------

    elif 6 * 60 <= current_minutes < sunset:

        draw.text(
            (95, 5),
            "DAY",
            font=font,
            fill="white"
        )

        draw_sun(
            draw,
            width // 2,
            55,
            25
        )


    # -----------------------------
    # Sunset: 7:00 PM - 7:30 PM
    # -----------------------------

    elif sunset <= current_minutes < 19 * 60 + 30:

        draw.text(
            (75, 5),
            "SUNSET",
            font=font,
            fill="orange"
        )

        draw_horizon_sun(
            draw,
            width // 2,
            75,
            25
        )


    # -----------------------------
    # Night
    # -----------------------------

    else:

        draw.text(
            (85, 5),
            "NIGHT",
            font=font,
            fill="white"
        )

        # Moon
        draw.ellipse(
            (100, 30, 145, 75),
            fill="white"
        )

        draw.ellipse(
            (115, 25, 150, 65),
            fill="black"
        )

        # Stars
        draw.ellipse((55, 35, 59, 39), fill="white")
        draw.ellipse((175, 50, 179, 54), fill="white")
        draw.ellipse((70, 70, 74, 74), fill="white")
        draw.ellipse((165, 25, 169, 29), fill="white")


    # -----------------------------
    # Date and time
    # -----------------------------

    draw.text(
        (65, 95),
        current_date,
        font=font,
        fill="white"
    )

    draw.text(
        (75, 115),
        current_time,
        font=font,
        fill="white"
    )


    # Display image
    disp.image(image, rotation)

    # Refresh once per second
    time.sleep(1)
