#!/usr/bin/env python3

'''
To be used on the SLAVE Rasperry Pi, to listen from trigger and record data.

This will listen for TTL pulses and record upon the the trigger
'''

import pigpio
from timeit import default_timer as timer
import numpy as np
import time
import argparse
# from picamera.array import PiRGBArray
from picamera import PiCamera
# import skvideo.io
import datetime
import pytz
import os

def newFile(workingDir): 
    '''
    This function will search in the working directory for a day folder.  
    If it does not find a folder wiht the date's name, it will create a 
    new folder. If the folder exisits the function will find the last
    file created.
    '''

    fnm  = datetime.datetime.now(pytz.timezone('US/Pacific')).strftime('%Y%m%d')[2:]
    path = workingDir + fnm

    #check to see if a file exists for the day on D drive
    if not os.path.exists(path):
        print('Making new directory:\n', path)
        os.makedirs(path)

    #Get the next filename in sequence for saving
    i = 1
    while os.path.exists(path + '/' + fnm + "_%02d_under.h264" % i):
        i += 1

    fnm_save = (path + '/' + fnm + '_%02d_under.h264' % i)

    return fnm_save , i

if __name__ == '__main__': 
    # construct the arguments parse and parse the arguments
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", "--fps", type=int, default=30,
        help="frame rate as frames per second")
    ap.add_argument("-l", "--length", type=float, default=1,
        help="Movie length in minutes")
    args = vars(ap.parse_args())


    wdir = '/home/pi/Desktop/Videos/'
    frameRate = args['fps']
    length = args['length'] * 60 # sec(s)
    # maxError = 10 # in milliseconds, any frame with at least this much error will be discarded
    camRes = (640, 480)
    camera = PiCamera(resolution=camRes,framerate=frameRate)


    # camera.hflip = True # For upside-down camera
    # camera.vflip = True # For upside-down camera
    # rawCapture = PiRGBArray(camera, size=camRes) # for easier use with OpenCV
    # writer = skvideo.io.FFmpegWriter(fnm)
    pi = pigpio.pi() #TTL

    fnm, i = newFile(wdir)

    print('File will be saved at:\n', fnm)

    try:
        print('Warming up camera')
        camera.color_effects = (128,128) # turn camera black and white
        camera.awb_gains = (1,1)
        camera.start_preview()
        time.sleep(5) # sleep 5 seconds to allow fo  the camera to warm up
        print('Camera ready! Waiting for trigger...')
        pi.wait_for_edge(18) # wait for trigger
        print('Recording to ' + fnm)
        t0 = time.time()
        camera.exposure_mode = 'night'
        camera.start_recording(fnm)
        time.sleep(length)
        camera.stop_recording()
        print("Recording took " + str(np.around(time.time() - t0, 2)) + " sec(s)")

        # for i in range(30): # this has a frequency of ~2 fps, better option?
            # t0 = timer()
            # camera.capture(frame, 'rgb')
            # writer.writeFrame(frame)
            # print(timer()-t0)

    finally:
          # writer.close()
          camera.stop_preview()
#print

