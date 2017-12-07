'''
stream_to_df0f_movie.py
    - for usb/computer camera: python stream_to_df0f_movie.py
    - for pi: python stream_to_dfof_movie.py -p 1
Default parameters save an .avi as a time stamped file ('YYYYMMDD_HHmm_dfof.avi').
Trackbars change the dfof colormap boundaries.  Each trackbar number coresponds to half a standard
    deviation of the dfof movie calculation.  Low end trackbar is divided between 8 divisions 
    (max 4 standard deviations from mean), whereas high end is divided between 16 divisions 
    (max 8 standard deviations from mean).  Low end moved right sets boundary closer to the 
    mean.  High end moved left sets boundary closer to the mean.
Keystrokes for controlling the recording vs streaming:
    r = start/stop record tsets
    esc = exit from while loop
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
import wholeBrain as wb
import math
import threading
import os
import csv

# construct the arguments parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-w", "--width", type=int, default=640,
                help="width size; height will be determined to keep proper frame ratio")
ap.add_argument("-l", "--length", type = float, default = 1,
                help="desired video length in minutes")
ap.add_argument("-f", "--fps", type=int, default=30,
                help="FPS of output video")
ap.add_argument("-s", "--setting", type = bool, default = False,
                help="Change camera settings")
ap.add_argument("-i", "--IPaddress", type = str, default = '',
                help="IP address for TCP connection")
ap.add_argument("-p", "--PORT", type = int, default = 8936,
                help="Port to bind TCP/IP or UDP connection")
args = vars(ap.parse_args())

def newFile():
    start_time = time.time()
    today = time.localtime()
    timeString  = time.strftime("%Y%m%d", today)

    fnm = timeString[2:].upper()
    path = '/home/ackmanlab/Videos/' + fnm
    # os.chmod(path[:-6], 0o777)

    #check to see if a file exists for the day on D drive
    if not os.path.exists(path):
        os.makedirs(path)
        # os.chmod(path, 0o777)
        print('Making new directory...\n')

    #Get the next filename in sequence for saving
    i = 1
    while os.path.exists(path + '/' + fnm + "_%02d_c1-0000.tif" % i):
        i += 1

    fnm_save = (path + '/' + fnm + '_%02d' % i)

    return fnm_save

#Regulates frame rate
# def fpsManager(t0, fps, verbose = False):
#     ta = timer() - t0
#     td = 1/(1.1*fps)
#     to = 0
#     if verbose == True:
#         print("Actual time:", round(ta, 4), "secs")
#         print("Desired time:", round(td, 4), "secs")
#         print("----------------------------------------")
#     if ta <= td:
#         ts = round(td - ta + to, 3)
#         if verbose == True:
#             print("Sleep time:", round(ts, 4), "secs")
#         time.sleep(ts)
#         to += timer() - t0 - td
#     if ta > td:
#         to -= timer() - t0 - td
#         print("Warning: Loop speed is slower than desired FPS by {0} sec".format(round(1/fps - ta, 4)))


def singleFrame(vis_during_rec = True):
    frame1 = vs1.read()
    frame1 = imutils.resize(frame1, args["width"])
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    if record == False or vis_during_rec == True:
        cv2.imshow('WebCam1: press r to record, q to quit', gray1)

    frame2 = vs2.read()
    frame2 = imutils.resize(frame2, args["width"])
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    if record == False or vis_during_rec == True:
        cv2.imshow('WebCam2: press r to record, q to quit', gray2)

    return gray1, gray2

host = args["IPaddress"]
port = args["PORT"]

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# s.connect((host, port))
s.bind((host, port))
print ("UDP socket bound to %s" %(port))

#initialize the video stream and allow the camera sensor to warmup

if args["setting"]:
    print("\nOpening camera settings GUI for camera 1")
    os.system('qv4l2 -d /dev/video0')
    print("\nOpening camera settings GUI for camera 2")
    os.system('qv4l2 -d /dev/video1')

print("\nWarming up camera and allocating memory\n-----------------------")

vs1 = WebcamVideoStream(src=0).start()
vs2 = WebcamVideoStream(src=1).start()
# vs1 = VideoStream(src=0).start()
# vs2 = VideoStream(src=1).start()
time.sleep(2.0)

#initialize the FourCC, video writer, dimensions of the frame, and zeros array
fps = args["fps"]
record = False
frame1, _ = singleFrame()
(h, w) = frame1.shape[:2]
numframe = int(fps * args['length'] * 60)
tmem = (numframe * h * w)/(1024**2) # approxamate total memory in megabytes
print("Size of expected recording: ", numframe, h, w)
print("If recording is chosen, this will require {0} MGs of RAM.".format(tmem))
# ts = None
# toverflow = 0

#Allocate memory on HD
fnm_save = newFile()
c1 = np.zeros((numframe, h, w), dtype=np.uint8)
c2 = np.zeros((numframe, h, w), dtype=np.uint8)
tlog_fnm = (fnm_save + '_tlog.txt')
print('\nSaving time log file to :', tlog_fnm)
tlog = open(tlog_fnm, 'w')

print("\nInitialize streaming\n-----------------------")
n = 0
while True:
    t0 = timer()
    gray1, gray2 = singleFrame()
    if record == True:
        data, addr = s.recvfrom(1024)
        n = int(float(data.decode('utf-8')))
        if n == 0:
            print("Starting recording")
        
        c1[n] = gray1
        c2[n] = gray2
        tlog.write("%f\n" % timer())

        if (n % 10) == 0:
            print("Average frames per sec: {0} frames/sec".format(10/(timer() - rec_time)))
            rec_time = timer()

    if (numframe - 1) == n:
        break

    key = cv2.waitKey(1) & 0xFF
    if key == ord('r'): #go to recording component
        if record == False:
            record = True
            print("Waiting for trigger")
            rec_time = timer()
        elif record == True:
            record = False
    elif key == ord('q'):
        break

if record == True:
    tmem = (numframe * h * w)/(1024**2) # approxamate total memory in megabytes
    mall = 2000
    div = int((numframe * mall)/tmem)
    num_files = math.ceil(tmem / mall)

    for n in range (num_files):
        wb.saveFile(fnm_save + '_c1-%04d.tif' % n , c1[n*(div):(n+1)*(div)])
        wb.saveFile(fnm_save + '_c2-%04d.tif' % n , c2[n*(div):(n+1)*(div)])

print("\nShutting down\n-----------------------")
tlog.close()
vs1.stop()
vs2.stop()
s.close()
cv2.destroyAllWindows()
for i in range(5):
    cv2.waitKey(1)


