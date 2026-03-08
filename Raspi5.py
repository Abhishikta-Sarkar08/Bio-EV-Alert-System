"""
Raspberry Pi Full code (gpiozero version)
(Shon Swapnanil, ei comment er jayega ta update korte thakbiaccording to ki ki modifications korchhish iei code e)

Functions:

Fingerprint integration:-
    1. Read authentication status from Arduino Nano
    2. Trigger buzzer alarm on ALERT signal
    3. Send SMS using SIM900A GSM module
Push button integration (cholche)

Author: System Integration Workflow
"""

import serial
import time
from gpiozero import Buzzer
from gpiozero import Button

# ------------------------------------------------
# USER CONFIGURATION
# ------------------------------------------------

# Arduino serial port
ARDUINO_PORT = "/dev/ttyACM0"
ARDUINO_BAUD = 9600

# SIM900A serial port
GSM_PORT = "/dev/serial0"
GSM_BAUD = 9600

# Buzzer GPIO pin
BUZZER_PIN = 18

BUTTON_PIN = 17

# Alarm duration (seconds)
ALARM_DURATION = 20   # user adjustable

# Emergency phone numbers
PHONE_NUMBERS = [
    "+911234567890",
    "+919876543210"
]

# Emergency messages
EMERGENCY_MESSAGE1 = "ALERT: CYCLE BREACHED."
EMERGENCY_MESSAGE2 = "EMERGENCY ALERT: Immediate assistance required!"

# -----------------------------
# BUTTON SETUP
# -----------------------------

button = Button(BUTTON_PIN, pull_up=True)


def button_pressed():
    emergency_procedure()


button.when_pressed = button_pressed

# ------------------------------------------------
# HARDWARE INITIALIZATION
# ------------------------------------------------

# Initialize buzzer
buzzer = Buzzer(BUZZER_PIN)

# Initialize serial communication
arduino = serial.Serial(
    ARDUINO_PORT,
    ARDUINO_BAUD,
    timeout=1
)

gsm = serial.Serial(
    GSM_PORT,
    GSM_BAUD,
    timeout=1
)

time.sleep(2)

# ------------------------------------------------
# GSM FUNCTIONS
# ------------------------------------------------

CALL_DURATION = 20  # seconds per call

def send_sms(phone_number, message):
    """
    Send SMS using SIM900A AT commands
    """

    print(f"Sending SMS to {phone_number}")

    gsm.write(b'AT\r')
    time.sleep(1)

    gsm.write(b'AT+CMGF=1\r')   # Set text mode
    time.sleep(1)

    command = f'AT+CMGS="{phone_number}"\r'
    gsm.write(command.encode())
    time.sleep(1)

    gsm.write(message.encode())
    time.sleep(1)

    gsm.write(bytes([26]))  # CTRL+Z to send message
    time.sleep(5)


def send_alert_sms():
    """
    Send alert SMS to all stored phone numbers
    """

    for number in PHONE_NUMBERS:
        send_sms(number, EMERGENCY_MESSAGE)


# ------------------------------------------------
# BUZZER CONTROL
# ------------------------------------------------

def trigger_alarm(duration):
    """
    Activate buzzer for specified duration
    """

    print("Alarm triggered")

    buzzer.on()
    time.sleep(duration)
    buzzer.off()


# ------------------------------------------------
# MAIN PROGRAM LOOP
# ------------------------------------------------

def main():

    print("Security monitoring started...")

    while True:

        if arduino.in_waiting > 0:

            line = arduino.readline().decode().strip()

            if line:
                print("Arduino:", line)

            if line == "ALERT":

                trigger_alarm(ALARM_DURATION)

                send_alert_sms()

                print("Alert handled\n")


# ------------------------------------------------
# SAFE PROGRAM TERMINATION
# ------------------------------------------------

try:

    main()

except KeyboardInterrupt:

    print("\nProgram terminated by user")

finally:

    buzzer.off()
    arduino.close()
    gsm.close()
