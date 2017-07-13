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
from __future__ import print_function
from imutils.video import VideoStream
import numpy as np
import argparse
import imutils
import cv2
import time

today = time.localtime()
timeString  = time.strftime("%Y%m%d", today)

fnm = timeString[2:].upper() + '_USB_cam_.tiff'
fnm = "{0}{1}{2}_{3}{4}_raw.tiff".format(today.tm_year, today.tm_mon, 
    today.tm_mday, today.tm_hour, today.tm_min)
windowName = fnm[:-4].upper() + 'press esc to quit, and r to record.'

# construct the arguments parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--output", default = fnm,
                help="path to output video file")
ap.add_argument("-p", "--picamera", type=int, default=-1,
                help="whether or not the Raspberry Pi camera should be used")
ap.add_argument("-f", "--fps", type=int, default=15,
                help="FPS of output video")
ap.add_argument("-c", "--codec", type=str, default="MJPG", #XVID codec works on linux, not on apple.  MJPG works on both.
                help="codec of output video")
ap.add_argument("-w", "--width", type=int, default=600,
                help="width size; height will be determined to keep proper frame ratio")
ap.add_argument("-n", "--windowname", type=str, default= windowName,
               help="name of the window and trackbars")
args = vars(ap.parse_args())

#initialize the video stream and allow the camera sensor to warmup
print("Warming up camera...")
# vs = VideoStream(usePiCamera=args["picamera"] > 0).start()
vs = VideoStream(src=0).start()
time.sleep(2.0)

#initialize the FourCC, video writer, dimensions of the frame, and zeros array
fourcc = cv2.VideoWriter_fourcc(*args["codec"])
out = None
(h, w) = (None, None)
zeros = None
A = None
wait_time = None
record = False
WindowName = args["windowname"]

n=0
print("Initialize streaming")
while True:
    t0 = time.time()

    #grab the frame from the video stream and resize it to have a max width
    gray = vs.read()
    # frame = imutils.resize(frame, args["width"])
    # gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cv2.imshow(WindowName, gray)

    if record == True:
        output = np.zeros((h, w),dtype="uint8")
        output[0:h, 0:w] = gray
        #output = np.zeros((h, w, 3),dtype="uint8")
        #output[0:h, 0:w] = frame #grayscale movie
        out.write(output)
        cv2.imshow(WindowName + "_RECORDING", output)
        n+=1

        if (n % 100) == 0:
            print("The number of frames collected: {0} frames".format(n))
            print("Average frames per sec: {0} frames/sec".format(n/(time.time() - rec_time)))

    key = cv2.waitKey(1) & 0xFF
    if key == ord("r"): #go to recording component
        if record == False:
            record = True
            print("Start recording")
            if out is None:
                #store the image dimensions, initialize the video writer and construct the zeros array
                (h, w) = frame.shape[:2]
                out = cv2.VideoWriter(args["output"], fourcc, args["fps"],
                                         (w*2, h), True) # double width if we want to get two side by side videos
                zeros = np.zeros((h,w,3), dtype="uint8")
                rec_time = time.time()
        elif record == True:
            record = False
    elif key == 27:
        break

#cleanup
print("Shutting down")
cv2.destroyAllWindows()
for i in range(5):
    cv2.waitKey(1)
vs.stop()
out.release()