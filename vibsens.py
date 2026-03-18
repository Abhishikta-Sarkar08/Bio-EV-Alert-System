from gpiozero import Button
from signal import pause

# connect vibration sensor to GPIO17
sensor = Button(17, pull_up=True)

def vibration_detected():
    print("Vibration detected!")

# trigger when vibration occurs
sensor.when_pressed = vibration_detected

print("Monitoring vibration sensor... Press CTRL+C to stop.")

pause()
