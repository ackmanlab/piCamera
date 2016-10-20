'''
stream_to_df0f_movie.py
    - for usb/computer camera: python stream_to_df0f_movie.py
    - for pi: python stream_to_dfof_movie.py -p 1

Default parameters save an .avi as a time stamped file ('YYYYMMDD_HHmm_dfof.avi').

Trackbars change the dfof colormap boundries.  Each trackbar number coresponds to half a standard
    deviation of the dfof movie calculation.  Low end trackbar is divided between 8 divisions 
    (max 4 standard deviations from mean), whereas high end is divided between 16 divisions 
    (max 8 standard deviations from mean).  Low end moved right sets boundry closer to the 
    mean.  High end moved left sets boundry closer to the mean.

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

start_time = time.time()
today = time.localtime()
fnm = "{0}{1}{2}_{3}{4}_dfof.avi".format(today.tm_year, today.tm_mon, 
    today.tm_mday, today.tm_hour, today.tm_min)
windowName = fnm[:-4].upper()

# construct the arguments parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--output", default = fnm,
                help="path to output video file")
ap.add_argument("-p", "--picamera", type=int, default=-1,
                help="whether or not the Raspberry Pi camera should be used")
ap.add_argument("-f", "--fps", type=int, default=15,
                help="FPS of output video")
ap.add_argument("-c", "--codec", type=str, default="XVID",
                help="codec of output video")
ap.add_argument("-w", "--width", type=int, default=600,
                help="width size; height will be determined to keep proper frame ratio")
ap.add_argument("-n", "--windowname", type=str, default= windowName,
               help="name of the window and trackbars")
args = vars(ap.parse_args())

#define functions to be used
def deltafof(image, AveImage):
    dfof = image.astype("float32", copy=False)
    AveImage = AveImage.astype("float32", copy = False)
    dfof = cv2.divide(dfof, AveImage, dfof)
    dfof -= 1.0
    meanCmap = np.nanmean(dfof)
    stdCmap = np.nanstd(dfof)
    return dfof, meanCmap, stdCmap

def ColormapBoundry(image, mean, std, low, high):
    newMin = mean - 0.5*(8-low)*std
    newMax = mean + 0.5*high*std
    newSlope = 255.0/(newMax-newMin)
    cv2.subtract(image, newMin, image)
    cv2.multiply(image, newSlope, image)
    return image.astype("uint8", copy=False)

#initialize the video stream and allow the camera sensor to warmup
print("Warming up camera...")
vs = VideoStream(usePiCamera=args["picamera"] > 0).start()
time.sleep(2.0)

#initialize the FourCC, video writer, dimensions of the frame, and zeros array
fourcc = cv2.VideoWriter_fourcc(*args["codec"])
out = None
(h, w) = (None, None)
zeros = None
A = None
wait_time = None
record = False

#Collect a few frames to define initial dfof parameters
print("Determining initial dfof parameters")
i = 0
n = 60

while i < n:
     frame = vs.read()    
     frame = imutils.resize(frame, args["width"])
     gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

     if A is None:
         (h, w) = frame.shape[:2]
         A = np.zeros((n, h, w), dtype="uint8")


     A [i,:,:]= gray
     i += 1

sz = A.shape
A2 = np.reshape(A, (sz[0], A.size/sz[0])) 
frameMean = np.mean(A2,axis=0,dtype="float32")
A2 = A2.astype("float32", copy=False)

for i in range(sz[0]):
    A2[i,:] /= frameMean
    A2[i,:] -= 1.0

#initial parameters needed for while loop
meanCmap = np.nanmean(A2)
stdCmap = np.nanstd(A2)
frameMean = np.reshape(frameMean, (sz[1], sz[2]))

#Make window and trackbar
print("Making Trackbars")
WindowName = args["windowname"]
TrackbarNameA = WindowName + " Low End"
TrackbarNameB = WindowName + " High End"

cv2.namedWindow(WindowName)
cv2.createTrackbar(TrackbarNameA, WindowName, 0, 8, lambda e: None)
cv2.createTrackbar(TrackbarNameB, WindowName, 16, 16, lambda e: None)

#print("--- %s seconds since start---" % (time.time() - start_time))
rec_time = time.time()
toverflow = 0
#cv2.createTrackbar('dfof',frame ,0,255, nothing)
print("Initialize streaming")
while True:
    t0 = time.time()

    #grab the frame from the video stream and resize it to have a max width
    frame = vs.read()
    frame = imutils.resize(frame, args["width"])
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if i < n:
        AveFrame = frameMean
        meanColormap = meanCmap
        stdColormap = stdCmap
        dfof, meanCmap, stdCmap = deltafof(gray, AveFrame)
    elif i >= n:
        dfof, meanCmap, stdCmap = deltafof (gray, AveFrame)
        AveFrame = (((i-1)/i) * AveFrame) + (gray / i)
        meanColormap = (((i-1)/i) * meanColormap) + (meanCmap / i)
        stdColormap = (((i-1)/i) * stdColormap) + (stdCmap / i)

    i += 1

    #set Colorbar value
    TrackbarPosA = cv2.getTrackbarPos(TrackbarNameA, WindowName)
    TrackbarPosB = cv2.getTrackbarPos(TrackbarNameB, WindowName)

    # if TrackbarPosA >=TrackbarPosB:
    #     cv2.setTrackbarPos(TrackbarNameB, WindowName, TrackbarPosA + 1)

    dfof = ColormapBoundry(dfof, meanColormap, stdColormap, TrackbarPosA, TrackbarPosB)
    dfof = cv2.applyColorMap(dfof, cv2.COLORMAP_JET)

    #cv2.threshold(Image, TrackbarPos, 255, cv2.THRESH_BINARY, test)
    cv2.imshow(WindowName, dfof)

    if record == True:
        output = np.zeros((h, w * 2, 3),dtype="uint8")
        output[0:h, 0:w] = frame
        output[0:h, w:w*2] = dfof #dfof movie
        out.write(output)
        cv2.imshow(WindowName + "_RECORDING", output)

    #write the output frame to file
    if (i % 100) == 0:
        print("Time passed since streaming: %s sec" % (time.time() - rec_time))
        print("Expected time from iterations: %s sec" % ((i-n)/args["fps"]))


    key = cv2.waitKey(1) & 0xFF
    if key == ord("r"): #go to recording component
        if record == False:
            record = True
            print("Start recording")
            if out is None:
                #store the image dimensions, initialize the video writer and construct the zeros array
                (h, w) = frame.shape[:2]
                out = cv2.VideoWriter(args["output"], fourcc, args["fps"],
                                         (w * 2, h), True) # double width if we want to get two side by side videos
                zeros = np.zeros((h,w), dtype="uint8")
        elif record == True:
            record = False
    elif key == 27:
        break

    # t1 = time.time() - t0 + toverflow
    # if t1 <= 1/args["fps"]:
    #     ts = round(1/args["fps"] - t1, 1)
    #     toverflow = t1 + ts - 1/args["fps"]
    #     time.sleep(ts)
    #     #print (ts)
    # elif t1 > 1/args["fps"]:
    #     toverflow -= t1 - 1/args["fps"]
    #     print("Warning: Loop speed is slower than FPS {0}".format(t1))


#cleanup
print("Shutting down")
cv2.destroyAllWindows()
for i in range(5):
    cv2.waitKey(1)
vs.stop()
out.release()
