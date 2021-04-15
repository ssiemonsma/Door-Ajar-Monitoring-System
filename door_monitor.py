#!/usr/bin/python
# Imports for csv
import csv

# Imports to check if a file exists
import os.path
from os import path

# Imports for Sense Hat
from sense_hat import SenseHat, ACTION_RELEASED, ACTION_HELD, ACTION_PRESSED # Used to interact with Sense Hat

# Imports for IMU
import sys, getopt
import RTIMU
import os.path
import time
import math

# Imports for InfluxDB
from datetime import datetime
import serial
import requests

# InfluxDB Parameters
sensor_name = "door_status"
device_name = "Stephen"
influx_url = 'https://us-central1-1.gcp.cloud2.influxdata.com/'
organization = 'Iot - Team 1'
bucket = 'Door_Data'
precision = 'ms'
influx_token = 'ePoz-_IlRIYlaczxif-R0k05OGEt5HPh9f29FaX2_xkl5iA1wcjctd7YMSMK0Ux1RZ9QCTj5APQ0D64uPKa8sA=='

# Sense Hat initialization
sense = SenseHat()
sense.low_light = True			# Makes the light level more tolerable
sense.clear()

# IMU initialization
sys.path.append('.')
SETTINGS_FILE = "RTIMULib"
print("Using settings file " + SETTINGS_FILE + ".ini")
if not os.path.exists(SETTINGS_FILE + ".ini"):
	print("Settings file does not exist, will be created")
s = RTIMU.Settings(SETTINGS_FILE)
imu = RTIMU.RTIMU(s)
print("IMU Name: " + imu.IMUName())
if (not imu.IMUInit()):
    print("IMU initialization failed")
    sys.exit(1)
else:
    print("IMU initialization succeeded")

# Set Fusion parameters
imu.setSlerpPower(0.02)
imu.setGyroEnable(True)
imu.setAccelEnable(True)
imu.setCompassEnable(True)
poll_interval = imu.IMUGetPollInterval()
print("Recommended Poll Interval: %dmS\n" % poll_interval)

# Initialize I/O on Pi
import RPi.GPIO as GPIO        # Allows us to call our GPIO pins and names it just GPIO
GPIO.setmode(GPIO.BOARD)       # Set's GPIO pins to board GPIO numbering
REED_PIN = 7                   # Input pin for reed sensor
GPIO.setup(REED_PIN, GPIO.IN)  # Set our input pin to be an input

# Predefined colors
r = [255,0,0]   		# Red
g = [0,255,0]			# Green
m = [255,0,255]			# Magenta
black = [0,0,0]			# Black
white = [255,255,255]	# White

# Control variables for initialization
initialized = False 	    # Set to True to skip startup
angleShutHave = False      # After the angleShut is obtained, will be True
flag = False			    # Whenever the joystick is pressed, becomes True

# Calibration data - Used to map raw data to a value between 0d and 90d from full shut to full open
angleShut = 0			    # Raw angle when the door is shut (actually set during calibration)
angleOpen = 90			    # Raw angle when the door is fully open (actually set during calibration)
angleMax  = 90			    # Used to set the range of the door angle LED indicator

counter = 0				# Used for portioning out commands

# Executes action on joystick release. Used for calibration.

# todo - add functionality to repeat message until joystick is pressed
def released(event):
	global flag
	if event.action == ACTION_RELEASED:
		flag = True
		print("Processing... Please do not move the door.")

# Draws a rectangle of pixels on a 8x8 pixel grid
def draw(x1,x2,y1,y2,color):
	for x in range(x1, x2+1):
		for y in range(y1, y2+1):
			sense.set_pixel(x, y, color)

# Draws to the screen based on the given angle
def drawAngle(angleDraw):
	angleInterval = angleMax/8 			# Number of degrees needed to change the angle-LED bars

	if angleDraw < angleInterval and angleDraw > -1*angleInterval:  # Open less than 12.5% of maximum (with room for up to 12.5% miscalibration)
		draw(0, 7, 4, 7, black)
	elif angleDraw < 2*angleInterval:	# Open 12.5%-25% of maximum
		draw(0, 0, 4, 7, white)
		draw(1, 7, 4, 7, black)
	elif angleDraw < 3*angleInterval:	# Open 12.5%-25% of maximum
		draw(0, 1, 4, 7, white)
		draw(2, 7, 4, 7, black)
	elif angleDraw < 5*angleInterval:	# Open 25%-37.5% of maximum
		draw(0, 2, 4, 7, white)
		draw(3, 7, 4, 7, black)
	elif angleDraw < 6*angleInterval:	# Open 37.5%-50% of maximum
		draw(0, 3, 4, 7, white)
		draw(4, 7, 4, 7, black)
	elif angleDraw < 2*angleInterval:	# Open 50%-62.5% of maximum
		draw(0, 4, 4, 7, white)
		draw(5, 7, 4, 7, black)
	elif angleDraw < 7*angleInterval:	# Open 62.5%-75% of maximum
		draw(0, 5, 4, 7, white)
		draw(6, 7, 4, 7, black)
	elif angleDraw < 8*angleInterval: 	# Open 75%-87.5% of maximum
		draw(0, 6, 4, 7, white)
		draw(7, 7, 4, 7, black)
	elif angleDraw < 10*angleInterval:	# Open 87.5%-100% of maximum (with additional room for up to 12.5% of miscalibration)
		draw(0, 7, 4, 7, white)
	else:
		draw(0, 7, 4, 7, m)				# Error: Indicates recalibration required

# Initialization Process
if __name__== "__main__":
	previouslyCalibrated = path.exists('calibration_file.csv')

	if previouslyCalibrated:
		initialized = True
		with open('calibration_file.csv', 'r') as file:
			reader = csv.reader(file)
			for row in reader:
				angleShut = float(row[0])
				angleOpen = float(row[1])
	else:
		print("Must initialize Pi. Please shut the door, and press the joystick on the Raspberry Pi.")
		
while not initialized:
	if angleShutHave == False:
		sense.show_message("Shut Door & Press Joystick", scroll_speed=0.05)
	else: 
		sense.show_message("Open Door 90 Deg & Press Joystick", scroll_speed=0.05)

	sense.stick.direction_any = released
	if flag:
		if imu.IMURead():
			# Flush out IMU (Must be done to get good readings)
			while counter < 1000:
				counter = counter + 1
				if imu.IMURead():
					data = imu.getIMUData()
			fusionQPose = data["fusionQPose"]
			abvalue = +2.0 * (fusionQPose[3] * fusionQPose[0] + fusionQPose[1] * fusionQPose[2])
			cdvalue = +1.0 - 2.0 * (fusionQPose[0] * fusionQPose[0] + fusionQPose[1] * fusionQPose[1])
			
			
			if not angleShutHave:
				angleShut = math.degrees(math.atan(cdvalue/abvalue))
				angleShutHave = True
				print("Shut angle is: %f" % angleShut)
				print("Please open the door to 90 degrees, and press the joystick on the Raspberry Pi.")
			else:
				angleOpen = math.degrees(math.atan(cdvalue/abvalue))
				initialized = True
				print("Open angle is: %f" % angleOpen)
				
				print("Initialization complete.")
				with open('calibration_file.csv', mode='w') as calibration_file:
					calibration_writer = csv.writer(calibration_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
					calibration_writer.writerow([angleShut, angleOpen])
			counter = 0
			flag = False
		
# Formats a data point submission for InfluxDB		
def get_formatted_line(sensor, reading, value):
    line = "{},device={} {}={} {}"
    timestamp = str(int(datetime.now().timestamp() * 1000))
    return line.format(sensor, device_name, reading, int(value), timestamp)
   
# Transmits a data point to InfluxDB
def send_line(line):
    try:
        url = "{}api/v2/write?org={}&bucket={}&precision={}".format(influx_url, organization, bucket, precision)
        headers = {"Authorization": "Token {}".format(influx_token)}
        print('Transmitted: ', line)
        r = requests.post(url, data=line, headers=headers)
    except:
        e = sys.exc_info()[0]
        print('Error writing to InfluxDB!: ', e)
		
# Sends a door angle update to InfluxDB
def send_angle_update(door_angle):
	# Only sending angles in the "valid" range
	if door_angle < 0:
		door_angle = 0
	if door_angle > angleMax:
		door_angle = angleMax

	line = get_formatted_line(sensor_name, 'angle', door_angle)
	send_line(line)

OPEN_STATUS_UPDATE_INTERVAL = 5
timeOpenStatusSent = datetime.utcnow().timestamp() - OPEN_STATUS_UPDATE_INTERVAL	# Make it so it's already due to transmit the open status

# Sends a door open/closed status update to InfluxDB
def send_open_update(open_status):
	global timeOpenStatusSent
	timeOpenStatusSent = datetime.utcnow().timestamp()

	line = get_formatted_line(sensor_name, 'open', open_status)
	send_line(line)
			
# Global variable updated via an interrupt
door_open = not GPIO.input(REED_PIN)

def update_open_status(pin):
	global door_open
	
	door_open = not GPIO.input(pin)

	if door_open:
		draw(0,7,0,3,g)	# Green = open
	else:
		draw(0,7,0,3,r) # Red = closed
		
	send_open_update(door_open)
		
# Initialize open/closed status LEDs
update_open_status(REED_PIN)

# Interrupt occurs on both door opening and closing
GPIO.add_event_detect(REED_PIN, GPIO.BOTH, callback=update_open_status, bouncetime=200)

# Calibrated angle calculations
angleSlope = (angleOpen - angleShut)/90
angleIntercept = angleShut

# Main operation loop
while True:
	if door_open:
		# Read in IMU data
		if imu.IMURead():
			# Read in angle data
			data = imu.getIMUData()
			fusionQPose = data["fusionQPose"]
			abvalue = +2.0 * (fusionQPose[3] * fusionQPose[0] + fusionQPose[1] * fusionQPose[2])
			cdvalue = +1.0 - 2.0 * (fusionQPose[0] * fusionQPose[0] + fusionQPose[1] * fusionQPose[1])
			
			# Process angle data to normalize to door
			angleRaw = math.degrees(math.atan(cdvalue/abvalue))
			angleCalibrated = (angleRaw - angleIntercept)/angleSlope
			
			drawAngle(angleCalibrated)	# Update door angle LEDs

		# Print values to terminal every 10 cycles
		if counter == 10:
			print("Calibrated angle:", round(angleCalibrated))
			send_angle_update(angleCalibrated)
			counter = 0
		counter = counter + 1
	
	# Periodically send the door open/closed status
	if datetime.utcnow().timestamp() - timeOpenStatusSent > OPEN_STATUS_UPDATE_INTERVAL:
		send_open_update(door_open)
	
	# Delay based on IMU
	time.sleep(poll_interval*0.001)
