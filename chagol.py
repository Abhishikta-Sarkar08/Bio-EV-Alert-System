import gpiod
import time
from gpiod.line import Direction, Value

# GPIO pins (BCM numbering)
TRIG = 23
ECHO = 24
BUZZER = 26

CHIP_PATH = "/dev/gpiochip0"

chip = gpiod.Chip(CHIP_PATH)

# Request GPIO lines
request = chip.request_lines(
    consumer="distance-buzzer",
    config={
        TRIG: gpiod.LineSettings(direction=Direction.OUTPUT),
        ECHO: gpiod.LineSettings(direction=Direction.INPUT),
        BUZZER: gpiod.LineSettings(direction=Direction.OUTPUT),
    },
)

def get_distance():

    request.set_value(TRIG, Value.INACTIVE)
    time.sleep(0.002)

    # Trigger pulse
    request.set_value(TRIG, Value.ACTIVE)
    time.sleep(0.00001)
    request.set_value(TRIG, Value.INACTIVE)

    timeout = time.perf_counter() + 0.05

    # Wait for echo start
    while request.get_value(ECHO) == Value.INACTIVE:
        if time.perf_counter() > timeout:
            return None

    start = time.perf_counter()

    # Wait for echo end
    while request.get_value(ECHO) == Value.ACTIVE:
        if time.perf_counter() > timeout:
            return None

    stop = time.perf_counter()

    elapsed = stop - start

    distance_cm = (elapsed * 34300) / 2
    return distance_cm


def beep(duration):
    request.set_value(BUZZER, Value.ACTIVE)
    time.sleep(duration)
    request.set_value(BUZZER, Value.INACTIVE)


print("Distance monitor started. Press Ctrl+C to stop.")

try:

    while True:

        d = get_distance()

        if d is None:
            print("Sensor timeout")
            request.set_value(BUZZER, Value.INACTIVE)
            time.sleep(0.5)
            continue

        print(f"Distance: {d:.1f} cm")

       # if d < 20:
            # continuous beep
            #request.set_value(BUZZER, Value.ACTIVE)

        if d < 50:
            # fast beep
            beep(0.1)
            time.sleep(0.1)

        elif d < 500:
            # slow beep
            beep(0.1)
            time.sleep(0.4)

        else:
            request.set_value(BUZZER, Value.INACTIVE)
            time.sleep(0.5)

except KeyboardInterrupt:
    print("\nStopped by user")

finally:
    request.release()
    chip.close()
