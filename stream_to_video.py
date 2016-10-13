#for usb: python stream_to_movie.py -o example.avi
#for pi: python stream_to_movie.py -o example.avi -p 1


# Import the necessary packages
from __future__ import print_function
from imutils.video import VideoStream
import numpy as np
import argparse
import imutils
import time
import cv2

# construct the arguments parse and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--output", required=True,
                help="path to output video file")
ap.add_argument("-p", "--picamera", type=int, default=-1,
                help="whether or not the Raspberry Pi camera should be used")
ap.add_argument("-f", "--fps", type=int, default=20,
                help="FPS of output video")
ap.add_argument("-c", "--codec", type=str, default="XVID",
                help="codec of output video")
ap.add_argument("-w", "--width", type=int, default=480,
                help="width size; height will be determined to keep proper frame ratio")
args = vars(ap.parse_args())

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

#Collect frames to decide what is average, to define dfof parameters
print("Determining dfof parameters")
i = 1
n = 20

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
Amean = np.mean(A2,axis=0,dtype="float32")
A2 = A2.astype("float32", copy=False)

for i in range(sz[0]):
    A2[i,:] /= Amean
    A2[i,:] -= 1.0

print("Determine normalized colormap function")
meanA = np.nanmean(A2)
stdA = np.nanstd(A2)
print("mean: {0}, std: {1}".format(meanA,stdA))
newMin = meanA - 3*stdA
newMax = meanA + 7*stdA
newSlope = 255.0/(newMax-newMin)
Amean = np.reshape(Amean, (sz[1], sz[2]))
print("Amean shape: {0}".format(Amean.shape))
A2 = np.reshape(A2, sz)

#loop over frames from the video stream
print("Start recording")

while True:
    #grab the frame from the video stream and resize it to have a max width
    # of 300 pixels
    frame = vs.read()    
    frame = imutils.resize(frame, args["width"])
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    #check if the writer is None
    if out is None:
        #store the image dimensions, initialize the video writer,
        #and construct the zeros array
        (h, w) = frame.shape[:2]
        out = cv2.VideoWriter(args["output"], fourcc, args["fps"],
                                 (w * 2, h), True)# double these if we want to get two side by side videos
        zeros = np.zeros((h,w), dtype="uint8")

    #dfof calculation
    dfof = gray.astype("float32", copy=False)
    cv2.divide(dfof, Amean, dfof)
    dfof -= 1.0
    cv2.subtract(dfof, newMin, dfof)
    cv2.multiply(dfof, newSlope, dfof)
    dfof = dfof.astype("uint8", copy=False)
    dfof = cv2.applyColorMap(dfof, cv2.COLORMAP_JET)

    #write the output frame to file
    output = np.zeros((h, w * 2, 3),dtype="uint8")
    output[0:h, 0:w] = frame
    output[0:h, w:w*2] = dfof #dfof movie
    
    # write the output frame to file
    out.write(output)

    #show the frames
    #cv2.imshow("Frame", frame)
    cv2.imshow("Output", output)
    key = cv2.waitKey(1) & 0xFF

    #if the 'q' key was pressed, break from the loop
    if key == ord("q"):
        break

#do a bit of cleanup
print("Shutting down")
cv2.destroyAllWindows()
vs.stop()
out.release()
 
