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
    r = start/stop record
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
from hdf5manager import *
import threading

start_time = time.time()
today = time.localtime()
timeString  = time.strftime("%Y%m%d", today)

fnm = timeString[2:].upper()
path = '/home/ackmanadmin/Documents/piCamera/data/' + fnm + '.hdf5'

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
ap.add_argument("-s", "--sync", type = bool, #default = False,
                help="Communicate with a server?")
ap.add_argument("-i", "--IPaddress", type = str, default = '',
                help="IP address for TCP connection")
ap.add_argument("-p", "--PORT", type = int, default = 8936,
                help="Port to bind TCP/IP or UDP connection")
args = vars(ap.parse_args())

#Regulates frame rate
def fpsManager(t0, fps, verbose = False):
    ta = timer() - t0
    td = 1/(1.1*fps)
    to = 0
    if verbose == True:
        print("Actual time:", round(ta, 4), "secs")
        print("Desired time:", round(td, 4), "secs")
        print("----------------------------------------")
    if ta <= td:
        ts = round(td - ta + to, 3)
        if verbose == True:
            print("Sleep time:", round(ts, 4), "secs")
        time.sleep(ts)
        to += timer() - t0 - td
    if ta > td:
        to -= timer() - t0 - td
        print("Warning: Loop speed is slower than desired FPS by {0} sec".format(round(1/fps - ta, 4)))

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

sync = args['sync']
print ('Sync: ', sync)

if args["sync"] == True:
    host = args["IPaddress"]
    port = args["PORT"]
    
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # s.connect((host, port))
    s.bind((host, port))
    print ("UDP socket bound to %s" %(port))

#initialize the video stream and allow the camera sensor to warmup
print("Warming up camera")

vs1 = WebcamVideoStream(src=0).start()
vs2 = WebcamVideoStream(src=1).start()

time.sleep(2.0)

#initialize the FourCC, video writer, dimensions of the frame, and zeros array
fps = args["fps"]
frame1 = vs1.read()
frame1 = imutils.resize(frame1, args["width"])
(h, w) = frame1.shape[:2]
numframe = fps * args['length'] * 60
ts = None
toverflow = 0
record = False

#Allocate memory on HD
print("Allocating Memory")
f = hdf5manager(path)
f.save({'data_f': np.zeros((numframe, h, w), dtype=np.uint8)})
f.save({'data_b': np.zeros((numframe, h, w), dtype=np.uint8)})
f.open()

print("Initialize streaming")
time_stamp = np.zeros(numframe, dtype=np.float32)
n = 0

while True:
    t0 = timer()
    gray1, gray2 = singleFrame()
    if record == True:
        if args["sync"] == True: 
            data, addr = s.recvfrom(1024)
            n = int(float(data.decode('utf-8')))

        if args["sync"]  == False:
            fpsManager(t0, fps, verbose = False)
            n += 1
        
        f.f['data_f'][n] = gray1
        f.f['data_b'][n] = gray2

        if (n % 10) == 0:
            print("Average frames per sec: {0} frames/sec".format(10/(timer() - rec_time)))
            rec_time = timer()

    if (numframe - 1) == n:
        break

    key = cv2.waitKey(1) & 0xFF
    if key == ord('r'): #go to recording component
        if record == False:
            record = True
            print("Starting Recording")
            rec_time = timer()
        elif record == True:
            record = False
    elif key == ord('q'):
        break

print("Shutting down")
f.close()
vs1.stop()
vs2.stop()
s.close()
cv2.destroyAllWindows()
for i in range(5):
    cv2.waitKey(1)
