#!/usr/bin/env python3
"""
baseCapture.py

Last Edited: 8/9/2016

Lead Author[s]: Anthony Fong
Contributor[s]:


Description:

A parent class that acts as the base class for other capture ojects

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
import datetime
import threading
from queue import Queue


########## Definitions ##########

# Classes #

class CameraCapture:
    def __init__(self):
        """
        CameraCapture: An object that acts as a super class for other capture objects who capture frames in their own
                       way.

        Required Modules: time, datetime, io, queue, threading
        Required Classes: None
        Methods: startCapture, endCapture, resetCapture, newFile, setDimFPS, waitUntil, mergeLocks, mergeCamParams,
                 mergeReturnedData, __recorderTask

        Class Attributes
        none

        Object Parameters & Attributes
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
        returnedData: Information produced about the camera such as recoding state and frame rate.
        dimensionLock: A lock to prevent changing the resolution of the frame while the camera is capturing.
        sync: A synchronization event that causes the camera to start when the event is triggered.
        syncRecord: A synchronization event that causes the camera to start and record when the event is triggered.
        record: An event that starts recording.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        recorderThread: A thread that controls whether the frames are being recorded/saved.
        """
        # Naming
        self.fileList = ['']
        self.previousFile = ''
        self.extraFileCount = 1

        # Frame Handling
        self.frameList = []
        self.fps = 10
        self.width = 640
        self.height = 480
        self.frameStreamq = Queue()

        # Threading
        self.locks = {'paramLock': threading.Lock(), 'statsLock': threading.Lock(), 'stopFrameCap': threading.Event(),
                      'startRecording': threading.Event(), 'stopRecording': threading.Event()}
        self.camParams = {'Filename': 'Test_Trial', 'Set Start Record': False, 'Set Stop Record': False,
                          'Set Record': False, 'Sync Time': time.time(),
                          'Start Record Time': time.time(),
                          'End Record Time': time.time()}
        self.returnedData = {'True Mode': 0, 'Is Recording': False}
        self.dimensionLock = threading.Lock()
        self.sync = threading.Event()
        self.syncRecord = threading.Event()
        self.record = threading.Event()
        self.continueRunning = threading.Event()
        self.captureTask = None
        self.captureThread = None
        self.recorderThread = threading.Thread(target=self.__recorderTask)

    # Methods #
    def startCapture(self):
        """ startCapture: Start capturing frames and prints a conformation message."""
        self.continueRunning.set()  # Set the event that keeps the threads alive.
        self.captureThread.start()  # Starts the capture thread.
        self.recorderThread.start()  # Starts the record thread.
        print('Capture Started')  # Prints that the capture process has started.

    def endCapture(self):
        """ endCapture: Ends capturing frames and prints a conformation message."""
        self.continueRunning.clear()                        # Clears the event, instructing the threads to shutdown.
        self.locks['stopRecording'].set()
        self.camParams['Set Stop Record'] = False
        self.locks['startRecording'].set()
        self.captureThread.join()                           # Wait fot the capture thread to shutdown.
        self.recorderThread.join()                          # Wait for the recoder thread to shutdown.
        print('Capture Ended')                              # Print that the capture process has ended.

    def resetCapture(self):
        """ resetCapture: Restart the capture from an ended state and optionally change some parameters."""
        if not self.continueRunning.is_set():  # When not running or shutting down:
            self.locks['stopRecording'].clear()
            self.locks['startRecording'].clear()
            self.camParams['Set Stop Record'] = False
            self.camParams['Set Start Record'] = False
            self.recorderThread = threading.Thread(target=self.__recorderTask)
            self.captureThread = threading.Thread(target=self.captureTask)
            self.startCapture()  # Start the capture process regardless of changes.
        else:  # If still running then print a failure but not an error.
            print('Reset Failed: Close Down Capture Before Resetting!')

    def newFile(self):
        """
        newFile: Create a new video file for the recorder to save to using the Filename entry in the camera parameters.
        """
        # Get parameters for new file name.
        if len(self.frameList) > 10:
            self.frameList.pop(0)
        with self.locks['paramLock']:
            fileName = self.camParams['Filename']  # Safely get filename from camera parameters with parameter lock.
        today = datetime.datetime.now()  # Get the current time and date.

        # Generate a new filename.
        fileName += '_{:}-{:}-{:}'.format(today.month, today.day, today.year)
        if fileName == self.previousFile:  # If the filename is the same as the previous one add a number to it
            self.fileList.append(self.previousFile + '({:})'.format(self.extraFileCount))
            self.extraFileCount += 1  # Increase the number of extra files with the same name.
        else:
            self.fileList.append(fileName)  # Add the filename to the list of filenames used.
            self.previousFile = self.fileList[-1]  # Set the previous filename to the current one.
            self.extraFileCount = 1  # Reset the number of extra files with the same name.

    def setDimFPS(self, width, height, fps):
        """
        setDimFPS: Safely set the resolution and fps of the frames.

        Parameters:
        :param width: Frame width in pixels.
        :param height: Frame height in pixels.
        :param fps: The capture speed of the camera.
        """
        with self.dimensionLock:  # Safely change the width, height, and fps with the dimension lock.
            self.width = width  # Set width.
            self.fps = fps  # Set FPS.
            self.height = height  # Set height.

    def waitUntil(self, synctime, interrupt=threading.Event()):
        """
        waitUntil: Makes the processor wait until a certain time unless interrupted.

        Parameters:
        :param synctime: The time to wait untill.
        :param interrupt: A threading event that will end the waiting if triggered.
        """
        interrupt.wait(timeout=synctime - time.time())

    def mergeLocks(self, master):
        """
        mergeLocks: Merges the threading locks and events into a master dictionary and uses that instead.

        Parameters:
        :param master: The master dictionary where the camera parameters will be stored.
        """
        for key, value in self.locks.items():
            if key not in master:
                master[key] = value
        self.locks = master

    def mergeCamParams(self, master):
        """
        mergeCamParams: Merges the camera parameters into a master dictionary and uses that instead.

        Parameters:
        :param master: The master dictionary where the camera parameters will be stored.
        """
        for key, value in self.camParams.items():
            if key not in master:
                master[key] = value
        self.camParams = master

    def mergeReturnedData(self, master):
        """
        mergeReturnedData: Merges the returned data into a master dictionary and uses that instead.

        Parameters:
        :param master: The master dictionary where the camera parameters will be stored.
        """
        for key, value in self.returnedData.items():
            if key not in master:
                master[key] = value
        self.returnedData = master

    def __recorderTask(self):
        """
        __recorderTask: A private method that continuously checks whether the camera should be capturing or not. The
                        method stays in an infinite loop until a different thread clears the continueRunning event.
        """
        while self.continueRunning.is_set():                        # Setup infinite checking loop.
            # NOT RECORDING
            with self.locks['statsLock']:
                self.returnedData['Is Recording'] = False          # Safely sets to not recording.
            # Wait for start signal.
            self.locks['startRecording'].wait()                     # Wait for a thread to initiate recording.
            self.locks['stopRecording'].clear()                     # Clears the stop recording for next time.
            if not self.continueRunning.is_set():                   # Exits from loop when told to shutdown.
                break
            self.newFile()                                          # Create a new video file.
            # If there is there is a specific time to start recording account for it.
            while self.locks['startRecording'].is_set() and self.camParams['Set Start Record']:
                self.locks['startRecording'].clear()                # Clear start recording for next time
                with self.locks['paramLock']:
                    start = self.camParams['Start Record Time']     # Safely get the time to start recording.
                    self.camParams['Sync Time'] = start
                when = start - time.time()  # Get how much time from now until it starts.
                print('Starting Recording in {:}s'.format(when))    # Print when it will start recording.
                self.waitUntil(start-1, interrupt=self.locks['startRecording']) # Wait until time is up or if interrupted.
                # The interrupt makes it so if new orders from the user come it overrides the last orders.
                # This allows for either a new start time to be entered or for immediate recording.
            # If told to record immediately then:
            if self.locks['startRecording'].is_set():
                with self.locks['paramLock']:                       # Safely set the start record time to now.
                    self.camParams['Start Record Time'] = time.time()
                    self.camParams['Sync Time'] = self.camParams['Start Record Time']
            self.syncRecord.set()                                   # Set the capture to start a sync recording.
            self.locks['stopFrameCap'].set()                        # Reset frame capture to start recording.
            with self.locks['statsLock']:
                self.returnedData['Is Recording'] = True           # Safely set to recording.

            # RECORDING
            # Wait for stop signal.
            self.locks['stopRecording'].wait()                      # Wait for a thread to stop recording.
            self.locks['startRecording'].clear()                    # Clears the start recording for next time.
            # If there is there is a specific time to stop recording account for it.
            while self.locks['stopRecording'].is_set() and self.camParams['Set Stop Record']:
                self.locks['stopRecording'].clear()                 # Clear stop recording for next time.
                with self.locks['paramLock']:
                    end = self.camParams['End Record Time']         # Safely get the time to stop recording.
                when = end - time.time()    # Get how much time from now until it stops.
                print('Stopping Recording in {:}s'.format(when))    # Print when it will stop recording.
                self.waitUntil(end, interrupt=self.locks['stopRecording'])  # Wait until time is up or if interrupted.
                # The interrupt makes it so if new orders from the user come it overrides the last orders.
                # This allows for either a new stop time to be entered or for immediate stopping.
            self.record.clear()                                     # Tells the capture thread to stop saving frames.
            print('Stopping ' + self.fileList[-1])                  # Prints that the recording has stopped.