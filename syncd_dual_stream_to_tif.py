'''
syncd_dual_stream_to_tif.py
    - for usb/computer camera: python syncd_dual_stream_to_tif.py

This code requires an external trigger to sync devices.
    See 'sync_cpu_cam.py' for sample code

Default parameters save individual frames as .tifs (YYMMDD_XX_c#_fffff.tif).
    Y = Year
    M = Month
    D = Day
    X = Experiment number
    c# = camera number
    f = frame number

Keystrokes for controlling the recording vs streaming:
    r = start/stop record
    q = exit from while loop
Written by: Brian Mullen
'''

# Import the necessary packages
from imutils.video import VideoStream
from imutils.video import WebcamVideoStream
import numpy as np
import argparse
import imutils
import cv2
from timeit import default_timer as timer
import socket
import time
from hdf5manager import *
import os

start_time = time.time()
today = time.localtime()
timeString  = time.strftime("%Y%m%d", today)

fnm = timeString[2:].upper()
path = '/home/ackmanadmin/Documents/piCamera/data/' + fnm

if not os.path.exists(path):
    os.makedirs(path)
    print("Making new directory.")

i = 1
while os.path.exists(path + '/' + fnm + '_%02d_c1-00000.tif' % i):
    i += 1

fnm_save = path + '/' + fnm + '_%02d' % i

# construct the arguments parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--output", default = fnm,
                help="path to output video file")
ap.add_argument("-w", "--width", type=int, default=600,
                help="width size; height will be determined to keep proper frame ratio")
ap.add_argument("-l", "--length", type = float, default = 1,
                help="desired video length in minutes")
ap.add_argument("-f", "--fps", type=int, default=20,
                help="FPS of output video")
ap.add_argument("-s", "--sync", type = bool, default = True,
                help="Communicate with a server?")
ap.add_argument("-i", "--IPaddress", type = str, default = '',
                help="IP address for TCP connection")
ap.add_argument("-p", "--PORT", type = int, default = 8936,
                help="Port to bind TCP/IP or UDP connection")
args = vars(ap.parse_args())

#Capture one frame each from two seperate USB cameras
def singleFrame():
    frame1 = vs1.read()
    frame1 = imutils.resize(frame1, args["width"])
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    if record == False:
        cv2.imshow('WebCam1: press r to record, q to quit', gray1)

    frame2 = vs2.read()
    frame2 = imutils.resize(frame2, args["width"])
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    if record == False:
        cv2.imshow('WebCam2: press r to record, q to quit', gray2)

    return gray1, gray2

#Set up UDP connection
host = args["IPaddress"]
port = args["PORT"]

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((host, port))
print ("UDP socket bound to %s" %(port))

#initialize the video stream and allow the camera sensor to warmup
print("Warming up camera")

vs1 = WebcamVideoStream(src=1).start()
vs2 = WebcamVideoStream(src=2).start()

time.sleep(2.0)

#determine parameters needed for saving
fps = args["fps"]
frame1 = vs1.read()
frame1 = imutils.resize(frame1, args["width"])
(h, w) = frame1.shape[:2]
numframe = int(fps * args['length'] * 60)
record = False

print("Initialize streaming")
n = 0

while True:
    t0 = timer()
    gray1, gray2 = singleFrame()
    if record == True:
        if n == 0:
            print("Starting Recording")
        data, addr = s.recvfrom(1024)
        n = int(float(data.decode('utf-8')))

        cv2.imwrite(fnm_save + '_c1-%05d.tif' % n, gray1)
        cv2.imwrite(fnm_save + '_c2-%05d.tif' % n, gray2)
        
        if (n % 10) == 0:
            print("Average frames per sec: {0} frames/sec".format(10/(timer() - rec_time)))
            rec_time = timer()

    if (numframe - 1) == n:
        break

    key = cv2.waitKey(1) & 0xFF
    if key == ord('r'): #go to recording component
        if record == False:
            record = True
            print("Waiting for trigger.")
            rec_time = timer()
        elif record == True:
            record = False
    elif key == ord('q'):
        break

print("Shutting down")
vs1.stop()
vs2.stop()
s.close()
cv2.destroyAllWindows()
for i in range(5):
    cv2.waitKey(1)

# Write all tifs to HDF5 format

# if args["record"]==True:
#     print("Saving to HDF5")
#     f = hdf5manager(fnm_save + '.hdf5')
#     f.save({'data_f': np.zeros((numframe, h, w), dtype=np.uint8)})
#     f.save({'data_b': np.zeros((numframe, h, w), dtype=np.uint8)})
#     f.open()
#     for n in range(int(numframe)):
#         f.f['data_f'][n] = np.array(cv2.imread(fnm_save + '_c1-%05d.tif' % n, 0), dtype = 'uint8')
#         f.f['data_b'][n] = np.array(cv2.imread(fnm_save + '_c2-%05d.tif' % n, 0), dtype = 'uint8')
#         if (n%100)==0:
#             print('Saving frame:', n, ' of ', numframe)
#     f.close()
