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

# Imports for sending emails
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import re	# regular expressions
import getpass

# InfluxDB Parameters
sensor_name = 'door_status'
device_name = 'Stephen'
influx_url = 'https://us-central1-1.gcp.cloud2.influxdata.com/'
organization = 'Iot - Team 1'
bucket = 'Door_Data'
precision = 'ms'
influx_token = 'ePoz-_IlRIYlaczxif-R0k05OGEt5HPh9f29FaX2_xkl5iA1wcjctd7YMSMK0Ux1RZ9QCTj5APQ0D64uPKa8sA=='

# Sense Hat initialization
sense = SenseHat()
sense.low_light = True			# Makes the light level more tolerable
sense.clear()

# Initialize I/O on Pi
import RPi.GPIO as GPIO			# Allows us to call our GPIO pins and names it just GPIO
GPIO.setmode(GPIO.BOARD)		# Set's GPIO pins to board GPIO numbering
REED_PIN = 7					# Input pin for reed sensor
GPIO.setup(REED_PIN, GPIO.IN)	# Set our input pin to be an input

# Predefined colors
r = [255,0,0]   		# Red
g = [0,255,0]			# Green
m = [255,0,255]			# Magenta
black = [0,0,0]			# Black
white = [255,255,255]	# White

# Control variables for initialization
calibrated = False		# Set to True to skip startup
angleShutHave = False	# After the angleShut is obtained, will be True
flag = False			# Whenever the joystick is pressed, becomes True
sendEmail = False

# Calibration data - Used to map raw data to a value between 0 and 90/180 degrees, from full shut to full open
angleShut = 0	# Raw angle when the door is shut (actually set during calibration)
angleOpen = 90	# Raw angle when the door is fully open (actually set during calibration)
angleMax  = 90			    # Used to set the range of the door angle LED indicator (set during configuration)

counter = 0		# Used for portioning out commands

# Executes action on joystick release. Used for calibration.
def released(event):
	global flag
	if event.action == ACTION_RELEASED:
		flag = True
		print('Processing... Please do not move the door.')

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
	elif angleDraw < 1*angleInterval:	# Open 12.5%-25% of maximum
		draw(0, 0, 4, 7, white)
		draw(1, 7, 4, 7, black)
	elif angleDraw < 2*angleInterval:	# Open 12.5%-25% of maximum
		draw(0, 1, 4, 7, white)
		draw(2, 7, 4, 7, black)
	elif angleDraw < 3*angleInterval:	# Open 25%-37.5% of maximum
		draw(0, 2, 4, 7, white)
		draw(3, 7, 4, 7, black)
	elif angleDraw < 4*angleInterval:	# Open 37.5%-50% of maximum
		draw(0, 3, 4, 7, white)
		draw(4, 7, 4, 7, black)
	elif angleDraw < 5*angleInterval:	# Open 50%-62.5% of maximum
		draw(0, 4, 4, 7, white)
		draw(5, 7, 4, 7, black)
	elif angleDraw < 6*angleInterval:	# Open 62.5%-75% of maximum
		draw(0, 5, 4, 7, white)
		draw(6, 7, 4, 7, black)
	elif angleDraw < 7*angleInterval: 	# Open 75%-87.5% of maximum
		draw(0, 6, 4, 7, white)
		draw(7, 7, 4, 7, black)
	elif angleDraw < 9*angleInterval:	# Open 87.5%-100% of maximum (with additional room for up to 12.5% of miscalibration)
		draw(0, 7, 4, 7, white)
	else:
		draw(0, 7, 4, 7, m)				# Error: Indicates recalibration required

# Initialization Process
if __name__== '__main__':
	previouslyCalibrated = path.exists('calibration_file.csv')

	if previouslyCalibrated:
		calibrated = True
		with open('calibration_file.csv', 'r') as file:
			reader = csv.reader(file)
			for row in reader:
				angleShut = float(row[0])
				angleOpen = float(row[1])
				angleMax = float(row[2])
				device_name = row[3]

	else:
		# Prompt user for a device name, which is used a flag in InfluxDB
		device_name = input('Type a name for this sensor: ')
		
		# Read in the template dashboard JSON
		with open('template_dashboard.json', 'r') as file:
			template_dashboard = file.read()

		# Replace the device name in the dashboard JSOn
		dashboard = template_dashboard.replace('device_name', device_name)

		# Write the customized dashboard JSON
		with open('dashboard.json', 'w') as file:
			file.write(dashboard)

		# Prompt user for how far the door opens (90 or 180 degrees)
		max_angle_selected = False
		while not max_angle_selected:
			max_angle_selection = input('How far does this door open?\n\t1) 90 degrees\n\t2) 180 degrees\n')
			if max_angle_selection == '1':
				angleMax = 90
				max_angle_selected = True
			elif max_angle_selection == '2':
				angleMax = 180
				max_angle_selected = True
			else:
				print('Invalid selection. Please choose 1 or 2.')

		# Prompt user for an email address
		valid_email_entered = False
		while not valid_email_entered:
			receiving_address = input('Enter an email address to receive an email with instructions for setting up an InfluxDB dashboard with a provided template file: ')
			
			if re.search('^(\w|\.|\_|\-)+[@](\w|\_|\-|\.)+[.]\w{2,3}$', receiving_address):
				valid_email_entered = True
				
		sendEmail = True  # Can't send email immmediately since it causes some sort of issue with calibration
			
		sending_address = 'iotdoormonitor@gmail.com'
		sending_address_password = getpass.getpass('Enter the password provided to you with this sensor in order to receive the email: ')

		# Create the email
		msg = MIMEMultipart()
		msg['From'] = sending_address
		msg['To'] = receiving_address
		msg['Subject'] = 'Door Monitor InfluxDB Dashboard'
		email_body = 'If you have already been granted access to the InfluxDB database, you can access it at https://us-central1-1.gcp.cloud2.influxdata.com/orgs/cddfaf76e097e685/dashboards-list and import the attached JSON to create a custom dashboard for the door monitoring device you are setting up.'
		msg.attach(MIMEText(email_body, 'plain'))
		attachment = open('./dashboard.json', 'rb')
		p = MIMEBase('application', 'octet-stream')
		p.set_payload((attachment).read())
		encoders.encode_base64(p)
		p.add_header('Content-Disposition', 'attachment; filename= %s' % 'dashboard.json')
		msg.attach(p)
		  
		# Send the email
		s = smtplib.SMTP('smtp.gmail.com', 587)
		s.starttls()  # Using TLS for security
		s.login(sending_address, sending_address_password)  
		s.sendmail(sending_address, receiving_address, msg.as_string())
		s.quit()

		os.remove('dashboard.json')
	
		print('Must initialize Pi. Please shut the door, and press the joystick on the Raspberry Pi.')
		
# IMU initialization
# (needs to occur after a possibly sending an email since that interferes with the IMU for some odd reason)
sys.path.append('.')
SETTINGS_FILE = 'RTIMULib'
if not os.path.exists(SETTINGS_FILE + '.ini'):
	print('Settings file does not exist, so it will be created.  Please complete IMU calibration for best accuracy!')
s = RTIMU.Settings(SETTINGS_FILE)
imu = RTIMU.RTIMU(s)
if (not imu.IMUInit()):
	print('IMU initialization failed.')
	sys.exit(1)

# Set Fusion parameters
imu.setSlerpPower(0.02)
imu.setGyroEnable(True)
imu.setAccelEnable(True)
imu.setCompassEnable(True)
poll_interval = imu.IMUGetPollInterval()
		
while not calibrated:
	if angleShutHave == False:
		sense.show_message('Shut Door & Press Joystick', scroll_speed=0.05)
	else: 
		sense.show_message('Open Door %i Deg & Press Joystick' % angleMax, scroll_speed=0.05)

	sense.stick.direction_any = released
	if flag:
		if imu.IMURead():
			# Flush out IMU (Must be done to get good readings)
			while counter < 1000:
				counter = counter + 1
				if imu.IMURead():
					data = imu.getIMUData()
			fusionQPose = data['fusionQPose']
			abvalue = +2.0 * (fusionQPose[3] * fusionQPose[0] + fusionQPose[1] * fusionQPose[2])
			cdvalue = +1.0 - 2.0 * (fusionQPose[0] * fusionQPose[0] + fusionQPose[1] * fusionQPose[1])
			
			
			if not angleShutHave:
				angleShut = math.degrees(math.atan(cdvalue/abvalue))
				angleShutHave = True
				print('Shut angle is: %f' % angleShut)
				print('Please open the door to %i degrees, and press the joystick on the Raspberry Pi.' % angleMax)
			else:
				angleOpen = math.degrees(math.atan(cdvalue/abvalue))
				calibrated = True
				print("Open angle is: %f" % angleOpen)
				
				print("Initialization complete.")
				with open('calibration_file.csv', mode='w') as calibration_file:
					calibration_writer = csv.writer(calibration_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
					calibration_writer.writerow([angleShut, angleOpen, angleMax, device_name])

			counter = 0
			flag = False
		
# Formats a data point submission for InfluxDB		
def get_formatted_line(sensor, reading, value):
	line = '{},device={} {}={} {}'
	timestamp = str(int(datetime.now().timestamp() * 1000))
	return line.format(sensor, device_name, reading, int(value), timestamp)
   
# Transmits a data point to InfluxDB
def send_line(line):
	try:
		url = '{}api/v2/write?org={}&bucket={}&precision={}'.format(influx_url, organization, bucket, precision)
		headers = {'Authorization': 'Token {}'.format(influx_token)}
		print('Transmitted: ', line)
		r = requests.post(url, data=line, headers=headers)
	except:
		e = sys.exc_info()[0]
		print('Error writing to InfluxDB!: ', e)
		sense.show_message('Error writing to InfluxDB!', scroll_speed=0.05)
		
# Sends a door angle update to InfluxDB
def send_angle_update(door_angle):
	# Only sending angles in the "valid" range
	if door_angle < 0:
		door_angle = 0
	if door_angle > angleMax:
		door_angle = angleMax

	line = get_formatted_line(sensor_name, 'angle', door_angle)
	send_line(line)

STATUS_UPDATE_INTERVAL = 5  # When door is closed, send updates only every 5 seconds
timeStatusSent = datetime.utcnow().timestamp() - STATUS_UPDATE_INTERVAL	# Make it so it's already due to transmit the open status

# Used for calculating statistics on individual opening events
openingMaxAngle = 0
openingTotalAngle = 0							# Used to calculate the average opening angle
openingTime = datetime.utcnow().timestamp()		# Will store when the door was last opened
OPENING_UPDATE_INTERVAL = 0.5					# When door is open, opening event statistics are updated every 0.5 seconds
openingTimeAngleCollected = datetime.utcnow().timestamp() - OPENING_UPDATE_INTERVAL	# Make it so it's already due to collect angle data

# Sends a door open/closed status update to InfluxDB
def send_open_update(open_status):
	global timeStatusSent
	timeStatusSent = datetime.utcnow().timestamp()

	line = get_formatted_line(sensor_name, 'open', open_status)
	send_line(line)
			
# Global variable updated via an interrupt routine
door_open = not GPIO.input(REED_PIN)

# Ran whenever the door opens or closes
def update_open_status(pin):
	global door_open
	
	door_open = not GPIO.input(pin)

	if door_open:
		draw(0,7,0,3,r)	# Red = open
		
		global openingTime, openingTimeAngleCollected
		openingTime = datetime.utcnow().timestamp()
		openingTimeAngleCollected = datetime.utcnow().timestamp() - OPENING_UPDATE_INTERVAL	# Make it so it's already due to collect angle data (in the main loop)
	else:
		global openingMaxAngle, openingTotalAngle

		draw(0,7,0,3,g) # Green = closed

		send_angle_update(0)	# When door is closed, angle is assumed to be 0 degrees

		# Send statistics for the opening event
		totalTimeOpen = datetime.utcnow().timestamp() - openingTime
		line = get_formatted_line(sensor_name, 'opening_time', totalTimeOpen)
		send_line(line)
		line = get_formatted_line(sensor_name, 'avg_opening_angle', openingTotalAngle/totalTimeOpen*OPENING_UPDATE_INTERVAL)
		send_line(line)
		line = get_formatted_line(sensor_name, 'max_opening_angle', openingMaxAngle)
		send_line(line)

		# Reset statistics for opening events
		openingMaxAngle = 0
		openingTotalAngle = 0	# Used to calculate the average opening angle
		
	send_open_update(door_open)
		
# Initialize open/closed status LEDs
update_open_status(REED_PIN)

# Interrupt occurs on both door opening and closing
GPIO.add_event_detect(REED_PIN, GPIO.BOTH, callback=update_open_status, bouncetime=200)

# Calibrated angle calculations
angleSlope = (angleOpen - angleShut)/angleMax
angleIntercept = angleShut

# Main operation loop
while True:
	if door_open:
		# Read in IMU data
		if imu.IMURead():
			# Read in angle data
			data = imu.getIMUData()
			fusionQPose = data['fusionQPose']
			abvalue = +2.0 * (fusionQPose[3] * fusionQPose[0] + fusionQPose[1] * fusionQPose[2])
			cdvalue = +1.0 - 2.0 * (fusionQPose[0] * fusionQPose[0] + fusionQPose[1] * fusionQPose[1])
			
			# Process angle data to normalize to door
			angleRaw = math.degrees(math.atan(cdvalue/abvalue))
			angleCalibrated = (angleRaw - angleIntercept)/angleSlope
			
			drawAngle(angleCalibrated)	# Update door angle LEDs
						
			if angleCalibrated > openingMaxAngle:
				openingMaxAngle = angleCalibrated

			if (datetime.utcnow().timestamp() - openingTimeAngleCollected) > OPENING_UPDATE_INTERVAL:
				openingTimeAngleCollected = datetime.utcnow().timestamp()
				openingTotalAngle += angleCalibrated

			# Send angle updates every 10 cycles
			if counter >= 10:
				print('Calibrated angle:', round(angleCalibrated))
				send_angle_update(angleCalibrated)
				counter = 0
			counter = counter + 1
	
	# Periodically send door status updates
	if datetime.utcnow().timestamp() - timeStatusSent > STATUS_UPDATE_INTERVAL:
		send_open_update(door_open)
		
		if not door_open:
			send_angle_update(0)	# When door is closed, angle is assumed to be 0 degrees
	
	# Delay based on IMU
	time.sleep(poll_interval*0.001)