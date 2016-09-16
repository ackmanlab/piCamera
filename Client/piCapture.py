#!/usr/bin/env python3
"""
baseCapture.py

Last Edited: 8/9/2016

Lead Author[s]: Anthony Fong
Contributor[s]:


Description:

A class that allows capturing and recording frames from a pi camera.

Machine I/O
input: none
output: none

User I/O
input: none
output: none

"""
###############################################################################


########## Librarys, Imports, & Setup ##########

# Default Libraries
import time
import threading
import io

# Downloaded Libraries
import picamera

# Custom Libraries
import baseCapture

########## Definitions ##########

# Classes #

class PiCameraCapture(baseCapture.CameraCapture):
    def __init__(self, frameType='jpeg'):
        """
        PiCameraCapture: An object that interacts with the Pi Camera to capture frames.

        Required Modules: time, io, queue, threading, picamera
        Required Classes: None
        Methods: startCapture, endCapture, resetCapture, newFile, setDimFPS, waitUntil, mergeLocks, mergeCamParams,
                 mergeReturnedData, __captureTask, __streams

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param frameType: The type file the frame will be encoded as.

        Attributes:
        File Naming:
        fileList: List of all the video file names used.
        previousFile: The previous video file name.
        extraFileCount: An extra number added to video file names when their name has been used multiple times.

        Frame Handling:
        frameList: An array of temporary buffers that store the raw frames after they come from the encoder.
        fps: The capture speed of the camera.
        width: Frame width in pixels.
        height: Frame height in pixels.
        frameStreamq: A queue to hold the raw frames to be processed.

        Threading and Timing:
        locks: The threading locks used by this object.
        camParams: The parameters for the camera.
        resetParams: A list of parameters that reset the camera.
        returnedData: Information produced about the camera such as recoding state and frame rate.
        dimensionLock: A lock to prevent changing the resolution of the frame while the camera is capturing.
        sync: A synchronization event that causes the camera to start when the event is triggered.
        syncRecord: A synchronization event that causes the camera to start and record when the event is triggered.
        record: An event that starts recording.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        captureThread: The thread that sets up capture and creates frames from the pi camera.
        recorderThread: A thread that controls whether the frames are being recorded/saved.
        """
        # Setup Parent Class Attributes
        super().__init__()

        # Parameters
        self.frameType = frameType

        # Threading
        self.camParams.update({'Mode': 0, 'X Resolution': 640, 'Y Resolution': 480, 'FPS': 30, 'Rotation': 0,
                               'Zoom': (0.0, 0.0, 1.0, 1.0), 'Shutter Speed': 0, 'ISO': 0, 'Meter Mode': 'average',
                               'Expo Comp': 0, 'Expo Mode': 'off', 'LED': False})
        self.resetParams = ['Mode', 'X Resolution', 'Y Resolution', 'FPS', 'Rotation', 'LED', 'Zoom', 'Shutter Speed',
                            'ISO', 'Meter Mode', 'Expo Comp', 'Expo Mode', 'LED', 'Filename']
        self.captureTask = self.__captureTask
        self.captureThread = threading.Thread(target=self.captureTask)

    # Methods #
    def __captureTask(self):
        """
        __captureTask: A private method that continuously captures frames and puts them into a queue for processing. The
                       method stays in an infinite loop until a different thread clears the continueRunning event.
        """
        # Setup Capture
        with picamera.PiCamera() as camera:         # Reserve the pi camera for this program's use.
            camera.led = False                      # Turn off the the camera's LED.
            # Capture Loop
            while self.continueRunning.is_set():    # Set up the infinite capture loop.
                # Setup the Camera
                self.locks['stopFrameCap'].clear()                # Clear the stop capture event.
                self.frameNumber = 0                # Clear the frame numbering system.
                self.frameList.clear()              # Clear the frames in the temporary array.
                with self.locks['paramLock']:                     # Safely get the parameters for the camera.
                    # Set the camera parameters properly.
                    # The parameters for the camera are relatively self explanatory. Check the picamera documentation
                    # for detailed explanations of the parameters.
                    camera.led = self.camParams['LED']
                    self.setDimFPS(self.camParams['X Resolution'], self.camParams['Y Resolution'],
                                   self.camParams['FPS'])
                    camera.resolution = (self.width, self.height)
                    camera.framerate = self.fps
                    camera.rotation = (self.camParams['Rotation'])
                    camera.shutter_speed = self.camParams['Shutter Speed']
                    camera.iso = self.camParams['ISO']
                    camera.meter_mode = self.camParams['Meter Mode']
                    camera.exposure_compensation = self.camParams['Expo Comp']
                    camera.exposure_mode = self.camParams['Expo Mode']
                    # Set a synchronization time to start the capture time at.
                    synctime = self.camParams['Sync Time']
                    # For statistics get the true camera mode.
                    with self.locks['statsLock']:
                        self.returnedData['True Mode'] = camera.sensor_mode
                # Setup the Capture Timing
                if self.syncRecord.is_set():        # If recording at sync time then:
                    self.syncRecord.clear()         # Reset sync recording for next time.
                    self.record.set()               # Set to record immediately when capturing.
                    print('Recording ' + self.fileList[-1])     # Notify recording the new file.
                    self.waitUntil(synctime)  # Wait until sync time.
                elif self.sync.is_set():              # When synchronizing capture times then:
                    self.sync.clear()               # Clear sync for next time.
                    self.waitUntil(synctime)        # Wait until sync time.
                else:
                    time.sleep(0.1)                 # In sync time then wait for the camera to warm-up.
                # Begin capturing frames with a sequence capture from pi camera.
                # Refer to the pi camera documentation on why this is the best why to record video.
                # The streams method acts as an infinite file-like-object generator that supplies temporary places to
                # store frames before they are processed and saved.
                camera.capture_sequence(self.__streams(), self.frameType, use_video_port=True)

    def __streams(self):
        """
        __streams: A private method that acts as an infinite file-like-object generator which supplies temporary places
                   to store frames before they are processed and saved. Also it puts these frames on a queue to be
                   processed.
        """
        # Generate frames as long as told to continue running and not told to reset frame capture.
        while (not self.locks['stopFrameCap'].is_set()) and self.continueRunning.is_set():
            self.frameList.append(io.BytesIO())     # Create a new place to store a frame.
            yield self.frameList[-1]                # Yield the byte stream to camera and go make a frame.
            self.frameNumber += 1                   # When done increase the number of frames captured
            # Put the frame on the queue with its information. The are some unsafe interactions for speed, be careful!
            # [Frame, width, height, FPS, frame number, current time, filename to save as, whether to save or not]
            self.frameStreamq.put([self.frameList.pop(), self.width, self.height, self.fps,
                                   self.frameNumber, time.time(), self.fileList[-1], self.record.is_set()])