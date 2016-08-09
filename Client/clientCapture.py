#!/usr/bin/env python3
"""
clientCapture.py

Last Edited: 8/9/2016

Lead Author[s]: Anthony Fong
Contributor[s]:


Description:
A program that takes frames produced by a camera of choice and processes them in based on a function determined by
imageProcess.py. Also it saves the information locally and can be controlled remotely via sockets.

Note: For this program "capture" means frames are produced by the camera, being temporarily stored, and worked on but
not saved to a file. "Recording" means that the captured frames are being saved to a file.

Variables:
consecutiveRuns: Represents whether the program with be on standby while not capturing.
quickStart: Represents whether the program will start capturing immediately or start in standby mode.
hostPort: A tuple with the IP Address of the server to send the information to and an arbitrary port outside the ones in
          use already.
camParams: The parameters for the camera.
ResetParams: The parameters that are require the camera to reset to change.
processParams: The parameters for processing the image.
returnedData: Statistical data produced by the objects.

When there are changes to the program be sure to check these variables for all the correct variables especially
processParams because that is subject to change based on algorithms in imageProcess. Just make sure all the possible
parameters are in processParam because it does not matter if there are extraneous variables in there as long as the
correct ones are present.

Main Thread and User Interaction:
To begin the objects are created and linked then the program starts running. If quickStart is active then the program
starts searching for a server, begins capturing, and frame management. Regardless the main thread waits for a command.
Most of the program can be controlled from a server when connected but it also can be controlled manually with commands.
The program will continuously capture until the server disconnects or the endCapture command is called. When not
capturing the program will be in stand by mode which only processes commands and runs threads when told to. The program
then only shuts down when the stopRunning command is called or when the server tells the program to shutdown after its
disconnected.

Threaded Object Interactions:
The server and socket objects operate in conjunction with the image capturing objects but are not reliant on them. The
ServerSeeker, object with ServerCommunicator, constantly searches for the server and sets the socket in which the
communicator will interact with the server. Also the seeker will set the file like socket object that the frameManager
will use to stream the frames across. The ServerCommunicator sends and receives information from the server which
dictates what the piCapture and FrameManager do.

For the image capture objects also operate in conjunction with the server and socket objects but are not reliant on
them. The piCapture object uses the piCamera to create frames with the designated parameters stored in a dictionary
that is accessible by multiple objects such as ServerCommunicator. These frames are stored in a queue which the
frameManager object has access to. With these frames the manager copies, saves, processes, and streams them with its
associated sub-objects. First the frames are taken from the queue and translated into a form that openCV can use. Then
one copy is sent to be saved if recording the other is sent to be processed. After processing the frame is saved if
recording and optionally streamed to the server. Along the way the frame is named and timestamped too.

Overall that means to capture frames piCameraCature and frameManager have to be on.


Machine I/O
input: none
output: A session dependent amount of files ranging from 0 to infinite.

User I/O
input: An optional command prompt for controlling the program.
output: none

Commands:

startSeek(): Starts the SeverSeeker object which tries to find the server designated by the hostname.
stopSeek(): Stops the ServerSeeker object.
startManagement(): Starts the FrameManager object which takes frames from a queue, saves, processes, and streams them.
stopManagement(): Stops the FrameManager object.
startCapture(): Starts the piCameraCapture object which captures frames and puts them on a queue
stopCapture(): Stops the piCameraCapture object.
printFPS(): Print the FPS that is currently being achieved.
printDelay(): Prints the delay of a frame being captured to when it is saved and processed.
endOthers(): Ends all other objects that have threads. (Communicator, ServerSeeker, PiCameraCapture, and FrameManager)
endProgram(): Ends the whole program. It will ask if you really want to do that.

startRecording(startTime=None): Starts recording.
    startTime: The time in seconds when to start recording from when this command executes.

stopRecording(stopTime=None, fromStart=False): Stops recording
    stopTime: The time in seconds when to stop recording from when this command executes.
    fromStart: The time in seconds when to stop recording from when recording started.

Changing Parameters Command:
[Parameter] = [New Value] : Change a camera parameter to a new value. Remember it is case sensitive.

Example:
FPS = 25
Set Stop Record = False


"""
###############################################################################


########## Librarys, Imports, & Setup ##########

# Default Libraries
import sys
import io
import time
import datetime
import socket
import struct
import re
import threading
from queue import Queue

# Downloaded Libraries
import picamera
import numpy
import cv2
import imageProcess


########## Definitions ##########

# Global Locks and Events #
paramLock = threading.Lock()
statsLock = threading.Lock()
connection_lock = threading.Lock()

startRecording = threading.Event()
stopRecording = threading.Event()
dataReceived = threading.Event()
stopFrameCap = threading.Event()
sendFrames = threading.Event()
sendServerData = threading.Event()


# Variables #
consecutiveRuns = True
quickStart = True
hostPort = ('128.114.78.67', 5555)
camParams = {'Mode': 0, 'X Resolution': 640, 'Y Resolution': 480, 'FPS': 30, 'Rotation': 0,
             'Zoom': (0.0, 0.0, 1.0, 1.0), 'Shutter Speed': 0, 'ISO': 0, 'Meter Mode': 'average', 'Expo Comp': 0,
             'Expo Mode': 'off', 'LED': False, 'Filename': 'Test_Trial', 'Set Start Record': False,
             'Set Stop Record': False, 'Set Record': False,
             'Sync Time': datetime.datetime.now().timestamp(),
             'Start Record Time': datetime.datetime.now().timestamp(),
             'End Record Time': datetime.datetime.now().timestamp()}
resetParams = {'Mode', 'X Resolution', 'Y Resolution', 'FPS', 'Rotation', 'LED', 'Zoom', 'Shutter Speed', 'ISO',
               'Meter Mode', 'Expo Comp', 'Expo Mode', 'LED', 'Filename'}
processParams = {'Function': 'value'}
returnedData = {'True Frame Rate': 0, 'Raw Frame Delay': 0, 'Processed Frame Delay': 0, 'True Mode': 0,
                'Is Recording': False}


# Classes #

class PiCameraCapture:
    def __init__(self, camParams, statsProduced={'True Mode': 0, 'Is Recording': False}, frameType='jpeg'):
        """
        PiCameraCapture: An object that interacts with the Pi Camera to capture frames.

        Required Modules: datetime, io, queue, threading, picamera
        Required Classes: None
        Methods: startCapture, endCapture, resetCapture, newFile, setDimFPS, waitUntil, __captureTask, __streams,
                 __recorderTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param camParams: The parameters for the camera defined by the picamera documentation.
        :param statsProduced: Information produced about the camera such as recoding state and frame rate.
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
        dimensionLock: A lock to prevent changing the resolution of the frame while the camera is capturing.
        sync: A synchronization event that causes the camera to start when the event is triggered.
        syncRecord: A synchronization event that causes the camera to start and record when the event is triggered.
        record: An event that starts recording.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        captureThread: The thread that sets up capture and creates frames from the pi camera.
        recorderThread: A thread that controls whether the frames are being recorded/saved.
        """
        # Parameters
        self.camParams = camParams
        self.statsProduced = statsProduced
        self.frameType = frameType

        # Naming
        self.fileList = []
        self.previousFile = ''
        self.extraFileCount = 1

        # Frame Handling
        self.frameList = []
        self.fps = 10
        self.width = 640
        self.height = 480
        self.frameStreamq = Queue()

        # Threading
        self.dimensionLock = threading.Lock()
        self.sync = threading.Event()
        self.syncRecord = threading.Event()
        self.record = threading.Event()
        self.continueRunning = threading.Event()
        self.captureThread = threading.Thread(target=self.__captureTask)
        self.recorderThread = threading.Thread(target=self.__recorderTask)

    # Methods #
    def startCapture(self):
        """ startCapture: Start capturing frames and prints a conformation message."""
        self.continueRunning.set()                          # Set the event that keeps the threads alive.
        self.captureThread.start()                          # Starts the capture thread.
        self.recorderThread.start()                         # Starts the record thread.
        print('Capture Started')                            # Prints that the capture process has started.

    def endCapture(self):
        """ endCapture: Ends capturing frames and prints a conformation message."""
        self.continueRunning.clear()                        # Clears the event, instructing the threads to shutdown.
        self.captureThread.join()                           # Wait fot the capture thread to shutdown.
        self.recorderThread.join()                          # Wait for the recoder thread to shutdown.
        print('Capture Ended')                              # Print that the capture process has ended.

    def resetCapture(self, camParams=None, statsProduced=None):
        """
        resetCapture: Restart the capture from an ended state and optionally change some parameters.

        Parameters:
        :param camParams: The parameters for the camera defined by the picamera documentation.
        :param statsProduced: Information produced about the camera such as recoding state and frame rate.
        """
        if not self.continueRunning.is_set():               # When not running or shutting down:
            if type(camParams) == dict:                     # And when new camera parameters entered:
                self.camParams = camParams                  # Then replace the camera parameters.
            if type(statsProduced) == dict:                 # And if there are new camera statistics:
                self.statsProduced = statsProduced          # Then replace the camera statistics.
            self.startCapture()                             # Start the capture process regardless of changes.
        else:                                               # If still running then print a failure but not an error.
            print('Reset Failed: Close Down Capture Before Resetting!')

    def newFile(self):
        """
        newFile: Create a new video file for the recorder to save to using the Filename entry in the camera parameters.
        """
        # Get parameters for new file name.
        with paramLock:
            fileName = self.camParams['Filename']   # Safely get filename from camera parameters with parameter lock.
        today = datetime.datetime.now()             # Get the current time and date.

        # Generate a new filename.
        fileName += '_{:}-{:}-{:}'.format(today.month, today.day, today.year)
        if fileName == self.previousFile:           # If the filename is the same as the previous one add a number to it
            self.fileList.append(self.previousFile + '({:})'.format(self.extraFileCount))
            self.extraFileCount += 1                # Increase the number of extra files with the same name.
        else:
            self.fileList.append(fileName)          # Add the filename to the list of filenames used.
            self.previousFile = self.fileList[-1]   # Set the previous filename to the current one.
            self.extraFileCount = 1                 # Reset the number of extra files with the same name.

    def setDimFPS(self, width, height, fps):
        """
        setDimFPS: Safely set the resolution and fps of the frames.

        Parameters:
        :param width: Frame width in pixels.
        :param height: Frame height in pixels.
        :param fps: The capture speed of the camera.
        """
        with self.dimensionLock:    # Safely change the width, height, and fps with the dimension lock.
            self.width = width      # Set width.
            self.fps = fps          # Set FPS.
            self.height = height    # Set height.

    def waitUntil(self, snyctime, interrupt=threading.Event()):
        """
        waitUntil: Makes the processor wait a certain amount of time unless interrupted.

        Parameters:
        :param snyctime: A timestamp of the time to wait till.
        :param interrupt: A threading event that will end the waiting if triggered.
        """
        while snyctime > datetime.datetime.now().timestamp():   # Stay in a loop until the time has passed.
            if interrupt.is_set():                              # Unless there is an interrupt from another thread.
                break                                           # Then exit the loop and continue processing.

    def __captureTask(self):
        """
        __captureTask: A private method that continuously captures frames and puts them into a queue for processing. The
                       method stays in an infinite loop until a different thread clears the continueRunning event.
        """
        # Setup Capture
        self.previousFile = ''                      # Clear the previous filename.
        self.extraFileCount = 1                     # Clear the extra file of the same name count.
        self.newFile()                              # Create a new video file to save to.

        with picamera.PiCamera() as camera:         # Reserve the pi camera for this program's use.
            camera.led = False                      # Turn off the the camera's LED.
            # Capture Loop
            while self.continueRunning.is_set():    # Set up the infinite capture loop.
                # Setup the Camera
                stopFrameCap.clear()                # Clear the stop capture event.
                self.frameNumber = 0                # Clear the frame numbering system.
                self.frameList.clear()              # Clear the frames in the temporary array.
                with paramLock:                     # Safely get the parameters for the camera.
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
                    if self.syncRecord.is_set():    # If recording at sync time then set record start immediately.
                        self.camParams['Start Record Time'] = datetime.datetime.now()
                    # For statistics get the true camera mode.
                    with statsLock:
                        self.statsProduced['True Mode'] = camera.sensor_mode
                # Setup the Capture Timing
                if self.syncRecord.is_set():        # If recording at sync time then:
                    self.syncRecord.clear()         # Reset sync recording for next time.
                    self.record.set()               # Set to record immediately when capturing.
                    print('Recording ' + self.fileList[-1])     # Notify recording the new file.
                if self.sync.is_set():              # When synchronizing capture times then:
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
        while (not stopFrameCap.is_set()) and self.continueRunning.is_set():
            self.frameList.append(io.BytesIO())     # Create a new place to store a frame.
            yield self.frameList[-1]                # Yield the byte stream to camera and go make a frame.
            self.frameNumber += 1                   # When done increase the number of frames captured
            # Put the frame on the queue with its information. The are some unsafe interactions for speed, be careful!
            # [Frame, width, height, FPS, frame number, current time, filename to save as, whether to save or not]
            self.frameStreamq.put([self.frameList.pop(), self.width, self.height, self.fps,
                                   self.frameNumber, datetime.datetime.now(), self.fileList[-1], self.record.is_set()])

    def __recorderTask(self):
        """
        __recorderTask: A private method that continuously checks whether the camera should be capturing or not. The
                        method stays in an infinite loop until a different thread clears the continueRunning event.
        """
        while self.continueRunning.is_set():                        # Setup infinite checking loop.
            # NOT RECORDING
            with statsLock:
                self.statsProduced['Is Recording'] = False          # Safely sets to not recording.
            # Wait for start signal.
            startRecording.wait()                                   # Wait for a thread to initiate recording.
            stopRecording.clear()                                   # Clears the stop recording for next time.
            self.newFile()                                          # Create a new video file.
            # If there is there is a specific time to start recording account for it.
            while startRecording.is_set() and self.camParams['Set Start Record']:
                startRecording.clear()                              # Clear start recording for next time
                with paramLock:
                    start = self.camParams['Start Record Time']     # Safely get the time to start recording.
                when = start - datetime.datetime.now().timestamp()  # Get how much time from now until it starts.
                print('Starting Recording in {:}s'.format(when))    # Print when it will start recording.
                self.waitUntil(start, interrupt=startRecording)     # Wait until time is up or if interrupted.
                # The interrupt makes it so if new orders from the user come it overrides the last orders.
                # This allows for either a new start time to be entered or for immediate recording.
            # If told to record immediately then:
            if startRecording.is_set():
                with paramLock:                                     # Safely set the start record time to now.
                    self.camParams['Start Record Time'] = datetime.datetime.now()
            self.syncRecord.set()                                   # Set the capture to start a sync recording.
            stopFrameCap.set()                                      # Reset frame capture to start recording.
            with statsLock:
                self.statsProduced['Is Recording'] = True           # Safely set to recording.
            # RECORDING
            # Wait for stop signal.
            stopRecording.wait()                                    # Wait for a thread to stop recording.
            startRecording.clear()                                  # Clears the start recording for next time.
            # If there is there is a specific time to stop recording account for it.
            while stopRecording.is_set() and self.camParams['Set Stop Record']:
                stopRecording.clear()                               # Clear stop recording for next time.
                with paramLock:
                    end = self.camParams['End Record Time']         # Safely get the time to stop recording.
                when = end - datetime.datetime.now().timestamp()    # Get how much time from now until it stops.
                print('Stopping Recording in {:}s'.format(when))    # Print when it will stop recording.
                self.waitUntil(end, interrupt=stopRecording)        # Wait until time is up or if interrupted.
                # The interrupt makes it so if new orders from the user come it overrides the last orders.
                # This allows for either a new stop time to be entered or for immediate stopping.
            self.record.clear()                                     # Tells the capture thread to stop saving frames.
            print('Stopping ' + self.fileList[-1])                  # Prints that the recording has stopped.


class FrameManager:
    def __init__(self, statsProduced={'True Frame Rate': 0}, processParams={'Parameters': 'values'}, frameType='jpeg',
                 clientSocket=None, rawFrameq=Queue()):
        """
        FrameManager: An object that accepts frames, processes them, and saves them.

        Required Modules: queue, threading, imageProcess
        Required Classes: ImageConverter, SavingThread, ImageProcess, ImageProcessor, ImageStreamer
        Methods: startManagement, endManagement, restartManagement, findAverageTime, connect2Server, __getRawTask,
                 __copyProTask, __statsTask

        Class Attributes
        none:

        Object Parameters & Attributes
        Parameters:
        :param statsProduced: A dictionary of the statistics produced by the frame manager.
        :param processParams: A dictionary of the parameters needed for processing a frame.
        :param frameType: The encoding of the raw frames.
        :param clientSocket: An optional socket to stream processed frames to.
        :param rawFrameq: A queue where the raw frames are being supplied.

        Attributes:
        statsq: A queue of the statistical information of each frame.

        Objects:
        frameConverter: An object that converts a frame of one type to another.
        rawSaver: An object that saves the raw frames.
        processedSaver: An object that saves the processed frames.
        timestampSaver: An object that saves the timestamps of each frame.
        processInfoSaver: An object that saves the information produced by the processed frames.
        processor: An object that process raw frames.
        streamer: An object that streams frames over a network through a socket.

        Threading:
        rawThreadCount: The number of threads used to prepare raw frames to be saved and processed.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        getRawThreadList: A list of threads used tp prepare raw frames to be saved and processed.
        proCopyThread: A thread that prepares processed frames to be saved and streamed.
        statsThread: A thread used to collect the statics on the frame management process.
        """
        # Parameters
        self.statsProduced = statsProduced
        self.clientSocket = clientSocket
        self.rawFrameq = rawFrameq
        # Attributes
        self.statsq = Queue()
        # Objects
        self.frameConverter = ImageConverter(frameType, 'BGR')
        self.rawSaver = SavingThread('video')
        self.processedSaver = SavingThread('video')
        self.timestampSaver = SavingThread('timestamp')
        self.processInfoSaver = SavingThread('processinfo')
        self.imageProcess = imageProcess.ImageProcess(processParams)
        self.processor = ImageProcessor(self.imageProcess.blankProcess, threadCount=2)
        if clientSocket:                                    # Create a VideoStreamer object if there was a socket.
            self.streamer = VideoStreamer(clientSocket, threadCount=2)
        else:
            self.streamer = None
        # Threads
        self.continueRunning = threading.Event()
        self.rawThreadCount = 4
        self.getRawThreadList = []
        for worker in range(self.rawThreadCount):           # Create the number of raw manager threads.
            self.getRawThreadList.append(threading.Thread(target=self.__getRawTask))
        self.proCopyThread = threading.Thread(target=self.__copyProTask)
        self.statsThread = threading.Thread(target=self.__statsTask)

    # Methods #
    def startManagement(self):
        """ startManagement: Starts managing in coming frames and prints a conformation message."""
        # Set threads to stay alive
        self.continueRunning.set()

        # Start Objects' Threads
        self.rawSaver.startSaving()
        self.processedSaver.startSaving()
        self.timestampSaver.startSaving()
        self.processInfoSaver.startSaving()
        self.processor.startProcessing()
        if self.clientSocket:                       # Start streamer if there is a socket.
            self.streamer.startStreaming()

        # Start Management Threads
        for worker in range(self.rawThreadCount):   # Start all raw manager threads.
            self.getRawThreadList[worker].start()
        self.proCopyThread.start()
        self.statsThread.start()
        print('Frame Management Started')           # Print that Management has started.

    def endManagement(self):
        """ endManagement: Ends managing frames and prints a conformation message. """
        # Wait until finished managing and instruct shutdown
        self.rawFrameq.join()                       # Wait until there are no new raw frames.
        self.continueRunning.clear()                # Set all threads to shutdown.

        # End raw frame preparing threads.
        for worker in range(self.rawThreadCount):   # Put blank data into rawFrameq to unblock threads.
            self.rawFrameq.put([None, None, None, None, None, None, None, None])
        for worker in range(self.rawThreadCount):   # Wait for all raw frame manager threads to shutdown.
            self.getRawThreadList[worker].join()

        # End raw video saver thread.
        self.rawSaver.endSaving()
        # End processing thread.
        self.processor.endProcessing()
        self.processor.processedq.join()
        self.processor.processedq.put([None, None, None, None, None, None, None, None, None])
        # End processed frame manager.
        self.proCopyThread.join()
        # End saving processed video, timestamps, and processed info.
        self.processedSaver.endSaving()
        self.timestampSaver.endSaving()
        self.processInfoSaver.endSaving()

        # End streaming thread if it exists
        if self.clientSocket:
            self.streamer.endStreaming()
            with connection_lock:
                self.clientSocket.write(struct.pack('<L', 0))   # Tell the server we are done streaming.
        print('Frame Management Ended')             # Print that the manager has shutdown.

    def resetManagement(self, statsProduced=None, clientSocket=None):
        """
        resetCapture: Restart the capture from an ended state and optionally change some parameters.

        Parameters:
        :param statsProduced: Information produced about the camera such as recoding state and frame rate.
        :param clientSocket: The socket to connect the streamer to.
        """
        if not self.continueRunning.is_set():           # When not running or shutting down:
            if type(statsProduced) == dict:             # And if there are new camera statistics:
                self.statsProduced = statsProduced      # Then replace the camera statistics.
            if clientSocket:                            # If there is a new socket.
                self.clientSocket = clientSocket        # Replace the with one.
                if not self.streamer:                   # If there no streamer create one.
                    self.streamer = VideoStreamer(clientSocket, threadCount=2)
            # Reset Objects' Threads
            self.rawSaver.resetSaving()
            self.processedSaver.resetSaving()
            self.timestampSaver.resetSaving()
            self.processInfoSaver.resetSaving()
            self.processor.resetProcessing()
            if self.streamer:                           # If there was streamer then restart it.
                self.streamer.resetStreaming(clientSocket=self.clientSocket)
            # Reset management threads.
            self.continueRunning.set()                  # Set threads to stay alive.
            self.statsThread.start()                    # Start the stats thread.
            for worker in range(self.rawThreadCount):   # Start the raw frame manager threads.
                self.getRawThreadList[worker].start()
            self.proCopyThread.start()                  # Start the processed frame manager thread.
            print('Frame Management Restarted')
        else:
            print('Reset Failed: Close Down Frame Management Before Resetting!')

    def findAverageTime(self, times, delay=True):
        """
        findAverageTime: Calculates the average FPS based on a list of timestamps.

        Parameters:
        :param time: List of times between each frame.
        :param delay: Calculates the average delay of capturing a frame to finishing processing the frame.
        :return: Either delay of a frame from capture to finished processing or the average FPS.
        """
        # Setup
        previoustime = 0                                     # The previous frame's timestamp.
        total = 0                                            # The total time of all frames. Either delay or FPS.
        # Repetitive Math
        for fstats in times:                                 # For all entries in the frames' timestamps.
            if delay:                                        # If the delay was selected:
                total += fstats[2]                           # Add the timestamp representing the delay time to total.
            else:                                            # If average FPS is desired:
                if previoustime:                             # And there was a previous frame
                    total += 1 / (fstats[1] - previoustime)  # Then add the frame rate between each frame to total.
                previoustime = fstats[1]                     # Set the current frame's timestamp to the previous one.
        # Divide the total by number of entries in list.
        if delay:
            return total / max(len(times), 1)
        else:
            return total / max(len(times) - 1, 1)            # Since fps is the time between frames there is one less.

    def connect2Server(self, clientSocket):
        """
        connect2Server: Tells the streamer to connect a server or creates a streamer if it does not exist.

        Parameter:
        :param clientSocket: The socket to connect to the server with.
        """
        if self.streamer:
            self.streamer.setServer(clientSocket)                       # Sets the server for the streamer.
        else:
            self.streamer = VideoStreamer(clientSocket, threadCount=2)  # Creates a streamer with assigned server.

    def __getRawTask(self):
        """
        __getRawTask: A thread task that takes a frame and its information from the raw frame queue and prepares it to
                     be saved and processed.
        """
        while self.continueRunning.is_set():            # Keep the thread running while true.
            # Get a raw frame and its information from the raw frame queue.
            frameStream, width, height, fps, frameNumber, timestamp, file, save = self.rawFrameq.get()

            # If it was something the do this:  (Since it is a blocking, Nones are loaded into the queue to unblock)
            if frameStream:
                # Convert the frame from a certain type to an OpenCV object, an BGR file.
                frameBGR = self.frameConverter.convert(frameStream.getbuffer(), width, height)
                # Send the frame to be processed.
                self.processor.processingq.put([frameBGR, width, height, fps, frameNumber, timestamp, file, save])

                # If the frame is to be saved. (Recording was on when the frame was captured):
                if save:
                    # Send raw frame be saved.
                    rawfile = file + 'Raw'              # Add an extra bit to filename to note this is a raw frame.
                    self.rawSaver.frameSaveq.put([frameBGR, width, height, fps, frameNumber, rawfile])
                    # Send timestamp to be saved.
                    timefile = file + 'Timestamps'      # Add an extra bit to filename to note this is a timestamp.
                    self.timestampSaver.frameSaveq.put([timestamp, width, height, fps, frameNumber, timefile])
                frameStream.close()                     # Close the bytestream object to free up memory.
                # Send statistical information to the stats thread via queue.
                self.statsq.put(['Raw', frameNumber, datetime.datetime.now().timestamp(), timestamp])

            # Regardless if the information was a frame or not.
            self.rawFrameq.task_done()                  # Tell the queue we are done with the given information.

    def __copyProTask(self):
        """
        __copyProTask: A thread task that takes a frame and its information from the processed frame queue and prepares
                       it to be saved and streamed.
        """
        # Keep the thread running while there are things to be processed or when told to live.
        while self.continueRunning.is_set() or self.processor.isAlive() or self.processor.hasProcessed():
            # Get a processed frame and its information from the raw frame queue.
            frameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save = self.processor.processedq.get()

            # If it was something the do this:  (Since it is a blocking, Nones are loaded into the queue to unblock)
            if frameNumber:
                # If streamer is present and told to stream then send frame to streamer.
                if sendFrames.is_set() and self.streamer:
                    self.streamer.sendFrameq.put([frameBGRnpa, frameNumber])

                # If the frame is to be saved. (Recording was on when the frame was captured):
                if save:
                    # Send processed frame be saved.
                    profile = file + 'Processed'        # Add an extra bit to filename to note this is a processed frame
                    self.processedSaver.frameSaveq.put([frameBGRnpa, width, height, fps, frameNumber, profile])
                    # Send processed frame information to be saved.
                    proInfofile = file + 'ProcessInfo'  # Add an extra bit to filename to note this is a processed info.
                    self.processInfoSaver.frameSaveq.put([information, width, height, frameNumber, timestamp, proInfofile])
                # Send statistical information to the stats thread via queue.
                self.statsq.put(['Pro', frameNumber, datetime.datetime.now().timestamp(), timestamp])

            # Regardless if the information was a frame or not.
            self.processor.processedq.task_done()       # Tell the queue we are done with the given information.

    def __statsTask(self):
        """
        __statsTask: A thread task that calculates and handles statistical information produced by the frame manager.
        """
        # Setup
        start = time.time()+10                                      # Sets the next time to calculate FPS and delay.
        trueFPS = []                                                # The list of frames' timestamp.
        rawTimes = []                                               # Timestamps from raw frames.
        proTimes = []                                               # Timestamps from processed frames.
        averfps = 0                                                 # Average FPS.

        while self.continueRunning.is_set():                        # Continuously do this while alive:
            stats = self.statsq.get()                               # Get stats from other threads.
            if stats:                                               # There are stats:
                # Get timestamp information.
                if stats[0] == 'Raw':                               # If from raw frame:
                    # Put raw timestamp information into a list with:
                    # [frame number, time finishing raw management, delay from capture to finishing raw management]
                    rawTimes.append([stats[1], stats[2], stats[2]-stats[3].timestamp()])
                    # Put raw FPS information into a list with:
                    # [frame number, time of frame capture]
                    trueFPS.append([stats[1], stats[3].timestamp()])
                else:                                               # If from processed frame:
                    # Put processed timestamp information into a list with:
                    # [frame number, time finishing pro management, delay from capture to finishing pro management]
                    proTimes.append([stats[1], stats[2], stats[2]-stats[3].timestamp()])

                # Every now and then calculate FPS and delay.
                if time.time() > start:                             # Once 10 seconds have passed:
                    # Sort the timestamps by frame order.
                    trueFPS.sort(key=lambda times: times[0])
                    rawTimes.sort(key=lambda times: times[0])
                    proTimes.sort(key=lambda times: times[0])
                    # Find the average delay from raw management and processing frames.
                    averRawDelay = self.findAverageTime(rawTimes)
                    averProDelay = self.findAverageTime(proTimes)
                    # Calculate FPS if there is more than one frame timestamp.
                    if len(trueFPS) > 1:
                        averfps = self.findAverageTime(trueFPS, delay=False)
                    # Safely updated the statistics for other threads to see.
                    with statsLock:
                        self.statsProduced['True Frame Rate'] = averfps
                        self.statsProduced['Raw Frame Delay'] = averRawDelay
                        self.statsProduced['Processed Frame Delay'] = averProDelay
                    # set
                    start = time.time()+10                          # Sets the next time to calculate FPS and delay.

            # Regardless if the information was a frame or not.
            self.statsq.task_done()                             # Tell the queue we are done with the given information.


class ImageConverter:
    def __init__(self, previous, new):
        """
        ImageConverter: An object that converts one image type to another.

        Required Modules: numpy, cv2
        Required Classes: None
        Parameters: previous, new
        Methods: deterTarget, convert, yuv420p2bgr, jpeg2bgr

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param previous: Previous image type to convert from. (String)
        :param new: New image type to convert to.   (String)

        Attributes
        conversionTable: A table that contain links to the methods for converting images which allows conversion
                                selection via indexing.
        row: The row that indexes to the conversion desired.
        column: The column that indexes to the conversion desired.
        """
        # Parameters
        self.previous = previous
        self.new = new
        # Attributes
        self.conversionTable = [[self.yuv420p2bgr, None], [self.jpeg2bgr, None]]
        self.row = None
        self.column = None
        # Initial Methods Executed
        self.deterTarget(previous, new)         # Determine and set the the conversion needed based on previous and new.

    # Methods #
    def deterTarget(self, previous, new):
        """
        deterTarget: Determines and sets the conversion of images types done by the object.

        Parameters:
        :param previous: Previous image type to convert from. (String)
        :param new: New image type to convert to.   (String)
        """
        # Determine if the previous image type is an available type and get its index.
        if previous.upper() == 'YUV420':
            self.row = 0
        if previous.upper() == 'JPEG':
            self.row = 1
        else:
            raise RuntimeError('Cannot convert from a ' + previous + ' type.')

        # Determine if the new image type is an available type and get its index.
        if new.upper() == 'BGR':
            self.columb = 0
        else:
            raise RuntimeError('Cannot convert to a ' + new + ' type.')

        # Set the attributes to the new ones
        self.previous = previous
        self.new = new

    def convert(self, frameBuffer, width, height):
        """
        convert: Converts one type of image to another by selecting the method that does so.

        Parameters:
        :param frameBuffer: The buffer that contains the image.
        :param width: The width of the image in pixels.
        :param height: The height of the image in pixels.
        :return: The same image of a different type based what was selected beforehand.
        """
        return self.conversionTable[self.row][self.column](frameBuffer, width, height)

    def yuv420p2bgr(self, frameBuffer, width, height):
        """
        yuv420p2bgr: Converts a YUV420p image to a BGR image.

        Parameters:
        :param frameBuffer: The buffer that contains the image.
        :param width: The width of the image in pixels.
        :param height: The height of the image in pixels.
        :return: A BGR numpy array of the frame.
        """
        # Calculate the actual image size in the frameBytes (accounting for rounding of the resolution)
        fwidth = (width + 31) // 32 * 32
        fheight = (height + 15) // 16 * 16
        frameArea = fwidth * fheight
        halfFrameArea = (fwidth // 2) * (fheight // 2)
        # Load the Y (luminance) data from the frameBytes
        Y = numpy.frombuffer(frameBuffer, dtype=numpy.uint8, count=frameArea).reshape((fheight, fwidth))
        # Load the UV (chrominance) data from frameBytes, and double its size
        U = numpy.frombuffer(frameBuffer, dtype=numpy.uint8, count=halfFrameArea, offset=frameArea).reshape(
            (fheight // 2, fwidth // 2)).repeat(2, axis=0).repeat(2, axis=1)
        V = numpy.frombuffer(frameBuffer, dtype=numpy.uint8, count=halfFrameArea, offset=frameArea+halfFrameArea).reshape(
            (fheight // 2, fwidth // 2)).repeat(2, axis=0).repeat(2, axis=1)
        # Stack the YUV channels together, crop the actual resolution, convert to floating point for later calculations, and apply the standard biases
        YUV = numpy.dstack((Y, U, V))[:height, :width, :].astype(numpy.float)
        YUV[:, :, 0] = YUV[:, :, 0] - 16  # Offset Y by 16
        YUV[:, :, 1:] = YUV[:, :, 1:] - 128  # Offset UV by 128
        # YUV conversion matrix from ITU-R BT.601 version (SDTV)
        #                   Y       U       V
        M = numpy.array([[1.164,  2.017,  0.000],   # B
                         [1.164, -0.392, -0.813],   # G
                         [1.164,  0.000,  1.596]])  # R
        # Take the dot product with the matrix to produce BGR output, clamp the results to byte range and convert to bytes
        return YUV.dot(M.T).clip(0, 255).astype(numpy.uint8)

    def jpeg2bgr(self, frameBuffer, width, height):
        """
        jpeg2bgr: Converts a JPEG image to a BGR image.

        Parameters:
        :param frameBuffer: The buffer that contains the image.
        :param width: The width of the image in pixels.
        :param height: The height of the image in pixels.
        :return: A BGR numpy array of the frame.
        """
        data = numpy.frombuffer(frameBuffer, dtype=numpy.uint8)     # Changes image to a NumPy array.
        return cv2.imdecode(data, 1)                                # Changes image to a BGR image.


class SavingThread:
    def __init__(self, type='video', fileFormat=None, encoder=None):
        """
        SavingThread: A threaded object that can save frames to videos, frames to files, timestamps, and information from
                      image processing.
        Required Modules: queue, threading, numpy, cv2
        Required Classes: None
        Methods: isSaving, startSaving, endSaving, resetSaving, _get_save_type, __saveVideoTask, __saveImageTask,
                 __saveTimestampsTask, __saveProcessTask

        Class Attributes
        none


        Object Parameters & Attributes
        Parameters:
        :param type: The type of saving to be done.
        :param fileFormat: For some saving types choose the file type to save the information as.
        :param encoder: The encoder used to save videos with.

        Attributes:
        frameSaveq: The queue where to get the incoming information that will be saved.
        continueRunning: A singal that keeps the saving thread alive.
        """
        # Parameters
        self.saveType = type
        # Use the strings from the parameters to choose the file format and encoder.
        self.fileFormat, self.encoder = self._get_save_type(type, fileFormat, encoder)
        # Attributes
        self.frameSaveq = Queue()
        self.continueRunning = threading.Event()

    # Methods #
    def isSaving(self):
        """ isSaving: Determines if there is still information to save."""
        return self.frameSaveq.unfinished_tasks     # Checks if there is still information in the queue to save.

    def startSaving(self):
        """ startSaving: Starts the saving thread and prints a conformation message."""
        if not self.continueRunning.is_set():                        # If the thread is not on:
            self.continueRunning.set()                               # Set thread to stay alive.
            self.saveThread.start()                                  # Start the saving thread.
            print('Saving {:} has started'.format(self.fileFormat))  # Print we have started saving.
        else:                                                        # If the thread was on then print we have failed.
            print('Start Failed: Close Down Saving Before starting!')

    def endSaving(self):
        """ endSaving: Ends the saving thread and prints a conformation message."""
        self.frameSaveq.join()                                      # Wait until there is nothing to save.
        self.continueRunning.clear()                                # Tell the saving thread to shutdown.
        self.frameSaveq.put([None, None, None, None, None, None])   # Load blank information to unblock thread.
        self.saveThread.join()                                      # Wait for saving thread to finish running.

    def resetSaving(self, type=None, fileFormat=None, encoder=None):
        """
        resetSaving: Restart saving from an ended state and optionally change some parameters.

        Parameters:
        :param type: The type of saving to be done.
        :param fileFormat: For some saving types choose the file type to save the information as.
        :param encoder: The encoder used to save videos with.
        """
        if not self.continueRunning.is_set():            # If the thread is not on:
            if type:                                     # If there is change in type:
                self.saveType = type                     # Set the new type and determine the file format and encoder.
                self.fileFormat, self.encoder = self._get_save_type(type, fileFormat, encoder)
            self.continueRunning.set()                   # Set thread to stay alive.
            self.saveThread.start()                      # Regardless of changes start the thread
            print('Saving {:} has restarted'.format(self.fileFormat))  # Print we have restarted saving.
        else:                                            # If the thread was on then print we have failed.
            print('Reset Failed: Close Down Saving Before Resetting!')

    def _get_save_type(self, type, fileFormat, encoder):
        """
        _get_save_type: Determine the type to save from strings defined in the parameters

        Parameters:
        :param type: The type of saving to be done.
        :param fileFormat: For some saving types choose the file type to save the information as.
        :param encoder: The encoder used to save videos with.
        """
        if type == 'video':                                                     # When saving a video:
            self.saveThread = threading.Thread(target=self.__saveVideoTask)     # Create a thread with the video task.
            fileFormat = '.' + (fileFormat or 'avi')                            # Choose the file format.
            encoder = tuple(ccFormat for ccFormat in (encoder or 'FFV1'))       # Choose the video encoder.
            encoder = cv2.VideoWriter_fourcc(*encoder)                          # Set the encoder.
        elif type == 'image':                                                   # When saving to images:
            self.saveThread = threading.Thread(target=self.__saveImagesTask)    # Create a thread with the image task.
            fileFormat = '.' + (fileFormat or 'tiff')                           # Choose the file format.
        elif type == 'timestamp':                                               # When saving timestamps:
            self.saveThread = threading.Thread(target=self.__saveTimestampsTask)  # Create a thread with the timestamps task.
            fileFormat = '.' + (fileFormat or 'txt')                            # Choose the file format.
            # Set the text inside the file.
            self.fileHeader = 'I do not know what to put in the header yet... Use your imagination!\n'
            self.subHeader = None
            self.lineText = 'Frame Number: {:}      Timestamp: {:}\n'
        elif type == 'processinfo':                                             # When saving processed info:
            self.saveThread = threading.Thread(target=self.__saveProcessInfoTask)  # Create a thread with the processed info task.
            fileFormat = '.' + (fileFormat or 'txt')                            # Choose the file format.
            # Set the text inside the file.
            self.fileHeader = 'I do not know what to put in the header yet... Use your imagination!\n'
            self.subHeader = 'Frame Number: {:}      Timestamp: {:}\n'
            self.lineText = None
        else:                                                                   # If not a type then don't make a thread.
            self.saveThread = None
        return fileFormat, encoder                                              # Return the file format and encoder.

    def __saveVideoTask(self):
        """
        __saveVideoTask: A thread task that takes frames and their information from the queue and saves them to a
                         video file.
        """
        # Setup
        previousFile = ''                                               # Previous name of the file.
        previousNumber = 0                                              # Previous frame number
        holdFrames = []                                                 # A list of frames to temporarily hold out of order frames.
        while self.continueRunning.is_set():                            # Continuously wait for a frame to save.
            # Wait for the frame and its information.
            frameBGRnpa, width, height, fps, frameNumber, file = self.frameSaveq.get()
            if frameNumber:                                             # If there was information:
                if not (file == previousFile):                          # And if the filename is different than the last.
                    # Set the openCV object to save the new video file.
                    self.currentVideo = cv2.VideoWriter(file+self.fileFormat, self.encoder, fps, (width, height), isColor=True)
                    previousFile = file                                 # Set the current filename to the previous one.
                    previousNumber = frameNumber-1                      # Set the previous frame to the one before this one.
                    holdFrames.clear()                                  # Clear any extra frames held in the out of order frames list.
                if frameNumber == previousNumber+1:                     # If this frame is the one after the last:
                    self.currentVideo.write(frameBGRnpa)                # Add this frame to video.
                    previousNumber += 1                                 # Set the previous frame number to this one.
                    for index in range(len(holdFrames)):                # Check all of the out of order frames:
                        frameBGRnpa, frameNumber = holdFrames.pop(0)    # Get the frame and its number.
                        if frameNumber == previousNumber + 1:           # If it is the next frame:
                            self.currentVideo.write(frameBGRnpa)        # Add it to the video.
                            previousNumber += 1                         # Advance a frame.
                        else:                                           # If it is not the next frame put it back.
                            holdFrames.insert(0, [frameBGRnpa, frameNumber])
                            break                                       # The list is ordered so all other frames will not match.
                else:                                                   # When the frame received is not the next one:
                    holdFrames.append([frameBGRnpa, frameNumber])       # Add it to the out of order frame list.
                    holdFrames.sort(key=lambda frame: frame[1])         # Order the list for ease of access.
            self.frameSaveq.task_done()                                 # Tell the queue we are done processing the information.

    def __saveImagesTask(self):
        """
        __saveImagesTask: A thread task that takes frames and their information from the queue and saves them to files.
        """
        while self.continueRunning.is_set():               # Continuously wait for a frame to save.
            # Wait for the frame and its information.
            frameBGRnpa, width, height, fps, frameNumber, file = self.frameSaveq.get()
            if frameNumber:                                # If there was information:
                # Add an extra piece to filename.
                filename = file + '{0}'.format(frameNumber)+self.fileFormat
                cv2.imwrite(filename, frameBGRnpa)         # Save the frame as an image.
            self.frameSaveq.task_done()                    # Tell the queue we are done processing the information.

    def __saveTimestampsTask(self):
        """ __saveTimestampsTask: A thread task that takes frame timestamps from the queue and saves it to a file."""
        holdFrames = []                                                         # A list of frames to temporarily hold out of order frames.
        # Get the first set of information.
        timestamp, width, height, fps, frameNumber, file = self.frameSaveq.get()
        while self.continueRunning.is_set():                                    # Continuously wait for a information to save.
            with open(file + self.fileFormat, 'w') as dataSheet:                # Open or create a text file.
                # Write the information to the file.
                dataSheet.write(self.fileHeader)
                dataSheet.write(self.lineText.format(frameNumber, timestamp))
                previousFile = file                                             # Set the previous filename to this one.
                previousNumber = frameNumber                                    # Set the previous frame number to this one.
                holdFrames.clear()                                              # Clear any extra frames held in the out of order frames list.
                self.frameSaveq.task_done()                                     # Tell the queue we are done processing the information.
                while self.continueRunning.is_set():                            # Continuously wait for a information to save.
                    # Get the first set of information.
                    timestamp, width, height, fps, frameNumber, file = self.frameSaveq.get()
                    if timestamp:                                               # If there was information:
                        if not (file == previousFile):                          # If there is a new file to save:
                            break                                               # Break out to create new text file.
                        if frameNumber == previousNumber + 1:                   # If this information is after the last:
                            # The write timestamp to file.
                            dataSheet.write(self.lineText.format(frameNumber, timestamp))
                            previousNumber += 1                                 # Set the previous number to this one.
                            for index in range(len(holdFrames)):                # Check all of the out of order frames:
                                frameBGRnpa, frameNumber = holdFrames.pop(0)    # Get the frame and its number.
                                if frameNumber == previousNumber + 1:           # If it is the next frame:
                                    # Write timestamp to file
                                    dataSheet.write(self.lineText.format(frameNumber, timestamp))
                                    previousNumber += 1                         # Advance a frame.
                                else:                                           # If it is not the next frame put it back.
                                    holdFrames.insert(0, [frameBGRnpa, frameNumber])
                                    break                                       # The list is ordered so all other frames will not match.
                        else:                                                   # When the frame received is not the next one:
                            holdFrames.append([timestamp, frameNumber])         # Add it to the out of order frame list.
                            holdFrames.sort(key=lambda frame: frame[1])         # Order the list for ease of access.
                        self.frameSaveq.task_done()                             # Tell the queue we are done processing the information.
                    else:
                        self.frameSaveq.task_done()                             # Tell the queue we are done processing the information.
                        break

    def __saveProcessInfoTask(self):
        """ __saveTimestampsTask: A thread task that takes frame timestamps from the queue and saves it to a file."""
        holdFrames = []                                                     # A list of frames to temporarily hold out of order frames.
        # Get the first set of information.
        information, width, height, frameNumber, timestamp, file = self.frameSaveq.get()
        while self.continueRunning.is_set():                                # Continuously wait for a information to save.
            with open(file + self.fileFormat, 'w') as dataSheet:            # Open or create a text file.
                # Write the information to the file.
                dataSheet.write(self.fileHeader)
                dataSheet.write(self.subHeader.format(frameNumber, timestamp))
                dataSheet.write(information.decode())
                dataSheet.write('\n')
                previousFile = file                                         # Set the previous filename to this one.
                previousNumber = frameNumber                                # Set the previous frame number to this one.
                holdFrames.clear()                                          # Clear any extra frames held in the out of order frames list.
                self.frameSaveq.task_done()                                 # Tell the queue we are done processing the information.
                while self.continueRunning.is_set():                        # Continuously wait for a information to save.
                    # Write the information to the file.
                    information, width, height, frameNumber, timestamp, file = self.frameSaveq.get()
                    if information:                                         # If there was information:
                        if not (file == previousFile):                      # If there is a new file to save:
                            break                                           # Break out to create new text file.
                        if frameNumber == previousNumber + 1:               # If this information is after the last:
                            # The write information to file.
                            dataSheet.write(self.subHeader.format(frameNumber, timestamp))
                            dataSheet.write(information.decode())
                            dataSheet.write('\n')
                            previousNumber += 1                             # Set the previous number to this one.
                            for index in range(len(holdFrames)):            # Check all of the out of order frames:
                                frameBGRnpa, frameNumber = holdFrames.pop(0)    # Get the frame and its number.
                                if frameNumber == previousNumber + 1:       # If it is the next frame:
                                    # Write timestamp to file
                                    dataSheet.write(self.subHeader.format(frameNumber, timestamp))
                                    dataSheet.write(information.decode())
                                    dataSheet.write('\n')
                                    previousNumber += 1                     # Advance a frame.
                                else:                                       # If it is not the next frame put it back.
                                    holdFrames.insert(0, [frameBGRnpa, frameNumber])
                                    break                                   # The list is ordered so all other frames will not match.
                        else:                                               # When the frame received is not the next one:
                            holdFrames.append([timestamp, frameNumber])     # Add it to the out of order frame list.
                            holdFrames.sort(key=lambda frame: frame[1])     # Order the list for ease of access.
                        self.frameSaveq.task_done()                         # Tell the queue we are done processing the information.
                    else:
                        self.frameSaveq.task_done()                         # Tell the queue we are done processing the information.
                        break


class ImageProcessor:
    def __init__(self, function, threadCount=1):
        """
        ImageProcessor:A threaded object that processes a frame.

        Required Modules: queue, threading
        Required Classes: None
        Methods: isAlive, isProcessing, hasProcessed, startProcessing, endProcessing, restartProcessing, __processingTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param function: The reference to function that the processor will use on each frame.
        :param threadCount: The number of threads that will be processing.

        Attributes:
        continueRunning: An event that keeps the threads alive.
        processingq: The queue that the image processor receives images from.
        processedq: The queue that the image processor put the processed images.
        threadList: The list of the threads used in the image processor.
        """
        # Parameters
        self.function = function
        self.threadCount = threadCount
        self.processParams = processParams
        # Attributes
        self.continueRunning = threading.Event()
        self.processingq = Queue()
        self.processedq = Queue()
        self.threadList = []
        # Create the threads.
        for worker in range(self.threadCount):
            self.threadList.append(threading.Thread(target=self.__processingTask))

    # Methods #
    def isAlive(self):
        """ isAlive: Determines if there are still threads processing."""
        for worker in range(self.threadCount):          # For all threads:
            if self.threadList[worker].is_alive():      # If there is a thread in list that is alive:
                return True                             # Return true.
        return False                                    # If all threads are dead then return false.

    def isProcessing(self):
        """ isProcessing: Determines if there are still frames to be processed."""
        return not self.processingq.empty()     # Check if there are frames in the queue.

    def hasProcessed(self):
        """ hasProcessed: Determines if there are frames any frames that have not been taken after being processed."""
        return not self.processedq.empty()      # Check if there are frames in the queue.

    def startProcessing(self):
        """ startProcessing: Starts the processing thread and prints a conformation message."""
        if not self.continueRunning.is_set():           # If the thread is not on:
            self.continueRunning.set()                  # Set threads to stay alive.
            for worker in range(self.threadCount):      # Start the processing threads.
                self.threadList[worker].start()
            print('Processing with {:} has started'.format(self.function))  # Print we have started processing.
        else:                                           # If the threads were on then print we have failed.
            print('Start Failed: Shutdown Processing Before Starting!')

    def endProcessing(self):
        """ endProcessing: Ends the saving threads and prints a conformation message."""
        self.processingq.join()                         # Wait for all the frames to be processed.
        self.continueRunning.clear()                    # Instruct all threads to shutdown.
        for worker in range(self.threadCount):          # For all threads load an unblocking empty data.
            self.processingq.put(None)
        for worker in range(self.threadCount):          # After all threads received there data, for all threads:
            self.threadList[worker].join()              # Wait for the threads to shutdown.

    def resetProcessing(self, function=None):
        """
        resetProcessing: Restart processing from an ended state and optionally change some parameters.

        Parameter:
        :param function: The reference to function that the processor will use on each frame.
        """
        if not self.continueRunning.is_set():           # If the thread is not on:
            if function:                                # If there is a new function then:
                for worker in range(self.threadCount):  # For all threads:
                    self.threadList[worker].join()      # Wait for the threads to shutdown.
                self.function = function                # Set the new function.
            self.continueRunning.set()                  # Set threads to stay alive.
            for worker in range(self.threadCount):      # Start the processing threads.
                self.threadList[worker].start()
                print('Processing with {:} has restarted'.format(self.function))  # Print we have restarted processing.
        else:                                           # If the threads were on then print we have failed.
            print('Start Failed: Shutdown Processing Before Restarting!')

    def __processingTask(self):
        """
        __processingTask: A thread task that takes frames and their information from the queue and processes them.
        """
        while self.continueRunning.is_set():                           # Continuously wait for a information to process.
            # data format: [frameBGRnpa, width, height, fps, frameNumber, timestamp, file, save]
            data = self.processingq.get()                              # Get data from to be processed queue.
            if data:                                                   # If there was data:
                results = self.function(self.processParams, data)      # Process that data with self.function.
                # results format: [frameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save]
                self.processedq.put(results)                           # Put results on the finished queue
            self.processingq.task_done()                               # Tell the queue we are done processing the information.


class VideoStreamer:
    def __init__(self, clientSocket, threadCount=1):
        """
        VideoStreamer: A threaded object that transmits frames over a socket.
        Required Modules: queue, threading, io, socket
        Required Classes: None
        Methods: isStreaming, setServer, startStreaming, endStreaming, restartStreaming, __streamingTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param clientSocket: The socket that the streamer will send the frames to.
        :param threadCount: The number of threads that will be processing.

        Attributes:
        continueRunning: An event that keeps the threads alive.
        sendFamesq: The queue that the image processor receives images from.
        threadList: The list of the threads used in the image processor.
        """
        # Parameters
        self.clientSocket = clientSocket
        self.threadCount = threadCount
        # Attributes
        self.continueRunning = threading.Event()
        self.sendFrameq = Queue()
        self.threadList = []
        # Create the threads
        for worker in range(self.threadCount):
            self.threadList.append(threading.Thread(target=self.__streamingTask))

    # Methods #
    def isStreaming(self):
        """ isStreaming: Determines if still streaming information."""
        return not self.sendFrameq.empty()

    def setServer(self, clientSocket):
        """
        setServer: Sets the socket to send the data across.

        Parameter:
        :param clientSocket: The socket that will be interacted with.
        """
        with connection_lock:                   # Safely access the client socket.
            self.clientSocket = clientSocket    # Set the socket to this one.

    def startStreaming(self):
        """ startStreaming: Starts the streaming threads and prints a conformation message."""
        if not self.continueRunning.is_set():               # If the thread is not on:
            self.continueRunning.set()                      # Set threads to stay alive.
            for worker in range(self.threadCount):          # Start the streaming threads.
                self.threadList[worker].start()
            print('Streaming to {:} has started'.format(self.clientSocket))  # Print we have started streaming.
        else:                                               # If the threads were on then print we have failed.
            print('Start Failed: Shutdown Streaming Before Starting!')

    def endStreaming(self):
        """ endStreaming: Ends the streaming threads and prints a conformation message."""
        self.sendFrameq.join()                      # Wait for all the frames to be streamed.
        self.continueRunning.clear()                # Instruct all threads to shutdown.
        for worker in range(self.threadCount):      # For all threads load an unblocking empty data.
            self.sendFrameq.put([None, None])
        for worker in range(self.threadCount):      # After all threads received there data, for all threads:
            self.threadList[worker].join()          # Wait for the threads to shutdown.

    def resetStreaming(self, clientSocket=None,):
        """
        resetStreaming: Restart streaming from an ended state and optionally change some parameters.

        Parameter:
        :param clientSocket: The socket that will be interacted with.
        """
        if not self.continueRunning.is_set():               # If the threads are not on:
            if clientSocket:                                # If there is a new socket then:
                self.setServer(clientSocket)                # Set the server
            self.continueRunning.set()                      # Set threads to stay alive.
            for worker in range(self.threadCount):          # Start the streaming threads.
                self.threadList[worker].start()
            print('Streaming to {:} has restarted'.format(self.clientSocket))  # Print we have started streaming.
        else:                                               # If the threads were on then print we have failed.
            print('Reset Failed: Close Down Streaming Before Resetting!')

    def __streamingTask(self):
        """ __streamingTask: A thread task that takes frames and streams them."""
        while self.continueRunning.is_set():                    # Continuously wait for a information to stream.
            frameBGRnpa, frameNumber = self.sendFrameq.get()    # Get data from to be frame queue.
            if frameBGRnpa:                                     # If there was data:
                stream = io.BytesIO(frameBGRnpa)                # Turn the data into a byte stream.
                try:                                            # Try to send data:
                    with connection_lock:                       # When socket is available:
                        # Inform the server we are sending data.
                        self.clientSocket.write(struct.pack('<L', stream.tell()))
                        self.clientSocket.flush()               # Remove any extra bytes in the socket.
                        stream.seek(0)                          # Go to the beginning of the byte stream.
                        self.clientSocket.write(stream.read())  # Write frame byte stream to socket.
                finally:
                    stream.seek(0)                              # When finished got to the beginning.
                    stream.flush()                              # Erase frame.
            self.sendFrameq.task_done()                         # Tell the queue we are done streaming the information.


class ServerCommunicator:
    def __init__(self, manager, camParams, resetParams, returnedData,
                 clientSocket=None, standAlone=False, encodeSize=20, sendDelay=1):
        """
        ServerCommunicator: A threaded object that communicates with a server.

        Required Modules: queue, threading, io, socket, struct
        Required Classes: ServerSeeker
        Methods: startCommunication, endCommunication, restartCommunication, disconnected, decodeMessage, setParams,
                 decodeParams, encodingMessage, __receivingTask, __sendTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters
        :param manager: The object that manages frames.
        :param camParams: Dictionary of parameters for the camera.
        :param resetParams: List of parameters that cause the camera to reset.
        :param returnedData: Dictionary of statistical data to send to the server.
        :param clientSocket: The socket that is used to communicate with the server.
        :param standAlone: A boolean that determines if this program will continue without the server.
        :param encodeSize: The max size of the key at the end of the encoded message used to communicate with the server.
        :param sendDelay: Time in seconds between sending information to the server.

        Attributes
        seeker: An object that finds the the server for the communicator.
        fmt: The format for key at the end of the encoded message used to communicate with the server.
        codeOffset: The length of the key for the encoded message used to communicate with the server.
        continueRunning: An event that keeps the threads alive.
        continueReceiving: An event that keeps the receiving thread alive.
        continueSending: An event that keeps the send thread alive.
        """
        # Parameters
        self.camParams = camParams
        self.resetParams = resetParams
        self.returnedData = returnedData
        self.clientSocket = clientSocket
        self.standAlone = standAlone
        self.sendDelay = sendDelay
        # Attributes
        self.seeker = ServerSeeker(hostPort, self, manager)
        self.fmt = '{:}s'.format(encodeSize)
        self.codeOffset = encodeSize * -1
        self.continueRunning = threading.Event()
        self.continueReceiving = threading.Event()
        self.continueSending = threading.Event()
        # Create Threads
        self.receivingThread = threading.Thread(target=self.__receivingTask)
        self.sendingThread = threading.Thread(target=self.__sendTask)

    # Methods #
    def startCommunication(self):
        """ startCommunication: Starts the communicating threads and prints a conformation message."""
        if not self.continueRunning.is_set():               # If the thread is not on:
            self.continueRunning.set()                      # Set threads to stay alive.
            self.continueReceiving.set()
            self.continueSending.set()
            # Start the threads
            self.receivingThread.start()
            self.sendingThread.start()
            print('Communicating with Server')              # Print we have started communication.
        else:                                               # If the threads were on then print we have failed.
            print('Start Failed: Shutdown Communication Before Starting!')

    def endCommunication(self):
        """ endCommunication: Ends the communicating threads and prints a conformation message."""
        self.continueRunning.clear()
        self.continueReceiving.clear()
        self.continueSending.clear()
        sendServerData.set()
        self.sendingThread.join()
        self.seeker.startSeeking()
        print('Communication ended')

    def resetCommunications(self, clientSocket=None, camParams=None, returnedData=None, encodeSize=20, sendDelay=1):
        """
        resetCommunication: Restart communicating from an ended state and optionally change some parameters.

        Parameters
        :param clientSocket: The socket that will be interacted with.
        :param camParams: Dictionary of parameters for the camera.
        :param returnedData: Dictionary of statistical data to send to the server.
        :param encodeSize: The max size of the key at the end of the encoded message used to communicate with the server.
        :param sendDelay: Time in seconds between sending information to the server.
        """
        if not self.continueRunning.is_set():           # If the threads are not on:
            if clientSocket:                            # If there is a new socket then:
                self.clientSocket = clientSocket        # Set the new socket.
            if type(camParams) == dict:                 # If there is are new camera parameters then:
                self.camParams = camParams              # Set camera parameters
            if type(returnedData) == dict:              # If there is are new statistics to return then:
                self.returnedData = returnedData        # Set returned data.
            self.fmt = '{:}s'.format(encodeSize)        # Set a new encoding format key if there is a change.
            self.codeOffset = encodeSize * -1           # Set the size of the new key if there is one.
            self.sendDelay = sendDelay                  # Set a new time between sending data to the server.
            self.startCommunication()                   # Starts communication with the server.
        else:                                           # If the threads were on then print we have failed.
            print('Reset Failed: Shutdown Communication Before Resetting!')

    def decodeMessage(self, message):
        """
        decodeMessage: Decodes a message based on the key on its tailing bytes.

        Parameters
        :param message: A message to decode using the key determined by fmt and codeOffset.
        """
        encoding = struct.unpack_from(self.fmt, message, offset=self.codeOffset)[0].decode('utf-8')
        self.setParams(list(struct.unpack(encoding + self.fmt, message)[:self.codeOffset]))

    def setParams(self, info):
        """
        setParams: Takes a structured list and changes the parameters used by other objects

        Parameters
        :param info: Takes list of information from a decoded message and changes the parameters.
        """
        # Setup
        reset = False
        record = False
        begin = False
        # The parameters are group in sets of 2. The first element is the key in the parameters dictionary. The the
        # actual data is in the second element. So odd elements are keys and even elements are data.
        for index in range(0, len(info), 2):
            if info[index] == 'Stand Alone':
                if info[index + 1]:
                    self.standAlone = True
                else:
                    self.standAlone = False
                continue
            elif info[index] == 'Record':
                record = True
                if info[index + 1]:
                    self.camParams['Set Start Record'] = False
                    begin = True
                else:
                    self.camParams['Set Stop Record'] = False
            elif info[index] == 'Set Record':
                record = True
                if info[index + 1]:
                    self.camParams['Set Start Record'] = True
                    begin = True
                else:
                    self.camParams['Set Stop Record'] = True
            elif info[index] == 'Stream':
                if info[index + 1]:
                    sendFrames.set()
                else:
                    sendFrames.clear()
            elif info[index] == 'Meter Mode' or info[index] == 'Expo Mode':
                # Meter mode and Expo mode need to be decoded some more.
                info[index + 1] = self.decodeParams(info[index], info[index + 1])
            with paramLock:
                self.camParams[info[index]] = info[index + 1]
            if info[index] in self.resetParams:
                reset = True
        # Reset the capture if told to.
        if reset:
            stopFrameCap.set()
        # Start or Stop the recording if told to.
        if record:
            if begin:
                startRecording.set()
            else:
                stopRecording.set()

    def decodeParams(self, type, data):
        """
        decodeParams: Extra decoding for meter mode and expo mode from a server message.

        Parameters
        :param type: The type of decoding to be done either Meter Mode or Expo Mode.
        :param data: The integer representation of the mode for meter or expo.
        :return: The mode that was decoded.
        """
        # For Meter Mode
        if type == 'Meter Mode':
            if data == 0:
                data = 'average'
            elif data == 1:
                data = 'spot'
            elif data == 2:
                data = 'backlit'
            else:
                data = 'matrix'
        # For Expo Mode
        elif type == 'Expo Mode':
            if data == 0:
                data = 'off'
            elif data == 1:
                data = 'auto'
            elif data == 2:
                data = 'night'
            elif data == 3:
                data = 'nightpreview'
            elif data == 4:
                data = 'backlight'
            elif data == 5:
                data = 'spotlight'
            elif data == 6:
                data = 'sports'
            elif data == 7:
                data = 'snow'
            elif data == 8:
                data = 'beach'
            elif data == 9:
                data = 'verylong'
            elif data == 10:
                data = 'fixedfps'
            elif data == 11:
                data = 'antishake'
            else:
                data = 'fireworks'
        return data

    def encodingMessage(self, toSend):
        """
        encodingMessage: Take data and encodes it to send via socket.

        Parameters
        :param toSend: The list of data to encode.
        :return: Byte encoded data to send.
        """
        # Setup
        fmt = ''                                                                    # The encoding format to fill.
        # Determine the type of each element and add it to the format using the struct rules.
        for item in toSend:
            if type(item) is str:
                fmt += str(len(item)) + 's'
            elif type(item) is int:
                fmt += 'H'
            else:
                fmt += 'f'
        # Append the format on end of the list.
        toSend.append(fmt + ' ' * (-self.codeOffset - len(fmt)))
        toSend = tuple(toSend)
        return struct.pack(fmt + self.fmt, *toSend)

    def _disconnected(self, error=None):
        """
        _disconnected: A method that handles when program is disconnected from the server.

        Parameters:
        :param error: A string that explains what error has occurred.
        """
        # Print the error.
        if error:
            print(error)
        print('Disconected From Server')

        # Set Stand Alone Mode
        if self.standAlone:
            print('Standing alone, control via commandline.')
        else:
            print('Ending Capture')

        # Set that communications have ended.
        self.continueSending.clear()
        self.continueReceiving.clear()
        self.continueRunning.clear()
        self.seeker.startSeeking()

    def __receivingTask(self):
        """ __receivingTask: A thread task that listens on the socket for information from the server."""
        while self.continueReceiving.is_set():                      # Continuously get messages from server.
            try:
                message = self.clientSocket.recv(2048)              # Wait for a message from the server.
            except socket.error as err:                             # If there is an error:
                self._disconnected(error=err)                       # Handle the disconnect.
                message = None                                      # There was no message.
            # Once a message has be received:
            if message:
                self.decodeMessage(message)                         # Decode the message.
                dataReceived.set()                                  # Tell other threads there was data received.

    def __sendTask(self):
        """ __sendTask: A thread task that sends information across the socket for the server take."""
        toEcode = []                                                    # Message to fill and send.
        while self.continueSending.is_set():                            # Continuously send messages from server.
            toEcode.clear()                                             # Remove extra data.
            time.sleep(self.sendDelay)                                  # Wait to send information the server.
            # Create a message to send
            with statsLock:                                             # Safely get statistics to send to server.
                items = list(self.returnedData.items())
            for index in range(len(items)):                             # Build the message as a singular list.
                toEcode.append(items[index][0])
                toEcode.append(items[index][1])
            sendToServer = self.encodingMessage(toEcode)                # Encode the message.
            # Try to send a message otherwise handle the disconnect.
            try:
                self.clientSocket.send(sendToServer)
            except socket.error as err:
                self._disconnected(error=err)


class ServerSeeker:
    def __init__(self, hostPort, communicator, manager, daemonic=True):
        """
        ServerSeeker: A threaded object that continuously tries to find a server.

        Required Modules: queue, threading, io, socket
        Required Classes: SeverCommunicator, FrameManager
        Methods: startSeeking, endSeeking, restartSeeking, __seekServerTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters
        :param hostPort: The port that the seeker will try to connect to.
        :param communicator: The communicator that will interact with the server.
        :param manager: The frame manager that controls what happens to the frames.
        :param daemonic: Determines if the thread will die when the main thread ends.

        Attributes
        continueRunning: An event that keeps the thread alive.
        clientSocket: The socket object that will send data through the socket to the server.
        clientConFile: A file like object that when writen to will send the data through the socket.
        seekingThread: The thread that seeks.
        """
        # Parameters
        self.hostPort = hostPort
        self.communicator = communicator
        self.manager = manager
        self.daemonic = daemonic
        # Attribute
        self.continueRunning = threading.Event()
        self.clientSocket = socket.socket()
        self.clientConFile = None
        # Create Thread
        self.seekingThread = threading.Thread(target=self.__seekServerTask)
        self.seekingThread.setDaemon(daemonic)

    def startSeeking(self):
        """ startStreaming: Starts the seeking thread and prints a conformation message."""
        if not self.continueRunning.is_set():                   # If the thread is not on:
            self.continueRunning.set()                          # Set threads to stay alive.
            self.seekingThread.start()                          # Start the seeking thread.
            print('Seeking has begun.')
        else:                                                   # If the thread was on then print we have failed.
            print('Start Failed: Shutdown Seeking Before Starting!')

    def endSeeking(self):
        """ endStreaming: Ends the streaming threads and prints a conformation message."""
        self.continueRunning.clear()                # Instruct all threads to shutdown.
        self.seekingThread.join()                   # Wait for thread to finish.

    def resetSeeking(self, hostPort=None, communicator=None, manager=None ):
        """
        resetStreaming: Restart streaming from an ended state and optionally change some parameters.

        Parameter:
        :param hostPort: The port that the seeker will try to connect to.
        :param communicator: The communicator that will interact with the server.
        :param manager: The frame manager that controls what happens to the frames.
        """
        if not self.continueRunning.is_set():
            if hostPort:
                self.hostPort = hostPort
            if communicator:
                self.communicator = communicator
            if manager:
                self.manager = manager
            self.continueRunning.set()
            self.seekingThread.start()
            print('Seeking has begun again.')
        else:
            print('Reset Failed: Shutdown Seeking Before Resetting!')

    def __seekServerTask(self):
        """ __seekServerTask: A thread task that seeks a server."""
        # If there is a socket with a connection already then close it.
        if self.clientConFile:
            self.clientConFile.close()
            self.clientSocket.close()
        # Seek a Server
        while self.continueRunning.is_set():                    # Continuously seek a server.
            try:
                self.clientSocket.connect(self.hostPort)        # Connect to server.
                self.continueRunning.clear()                    # Stop seeking because we found a server.
            except:                                             # Timeout may occur.
                continue                                        # Retry seeking.
        # When a server is found create file like object to write to and have the other objects connect to them.
        if self.clientSocket:
            self.clientConFile = self.clientSocket.makefile('wb')
            self.communicator.resetCommunications(clientSocket=self.clientSocket)
            self.manager.connect2Server(self.clientConFile)


class SudoCommandLine:
    def __init__(self, parameters=None, stats=None):
        """
        ServerSeeker: A threaded object that continuously tries to find a server.

        Required Modules: threading, socket
        Required Classes: None
        Methods:

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters
        :param parameters: Dictionary of the parameters used by other objects.
        :param stats: Dictionary of the statistics produced by other objects.

        Attributes
        changedParams: List of parameters changed by the user.
        commands: List of constructors and commands in the the object.
        #Flags
        globalCommands: Boolean if a command entered was a global command.
        startSeek: Boolean if a command entered was start seeking a server.
        stopSeek: Boolean if a command entered was stop seeking a server.
        stopRunning: Boolean if a command entered was stop running the program.
        endCapture: Boolean if a command entered was stop all other objects.
        """
        # Parameters
        self.parameters = parameters
        self.stats = stats
        # Attributes
        self.changedParams = []
        self.commands = dir(self)
        # Flags
        self.globalCommands = False
        self.startSeek = False
        self.stopSeek = False
        self.startManagement = False
        self.stopManagement = False
        self.startCapture = False
        self.stopCapture = False
        self.stopRunning = False
        self.endOthers = False

    def userInput(self):
        """ userInput: Waits for user input and executes commands based on what was entered."""
        self.changedParams.clear()
        # Wait for user input
        print('Enter Command: ')
        for line in sys.stdin:
            try:
                # Clean up inputted commands
                line = ''.join(line.splitlines()).strip()
                if not line == '':
                    commandList = self.splitParenthesis(line)
                    # Go through inputs and check if they were commands.
                    for command in commandList:
                        self.parseCommand(command)
                    # Once finished stop waiting an exit user input.
                    break
                else:
                    break
            except:
                print("Error: Not a Command!")
                print('Enter Command: ')

    def splitParenthesis(self, line):
        """
        splitParenthesis: Separates out commands based on commas, parenthesis, and other groupers.

        Parameter:
        :param line: The line from the user input to organize.
        :return: A list of commands that were parsed from the input.
        """
        # Setup
        groupers = [['{', '}', 0], ['(', ')', 0], ['[', ']', 0]]
        charlist = list(line)
        previous = 0
        commandList = []
        # Look for grouping and separate commands.
        for char in range(len(charlist)):
            for group in range(len(groupers)):
                # Check for grouping openers and add to the total grouper.
                if charlist[char] == groupers[group][0]:
                    groupers[group][2] += 1
                    break
                # Check for grouping for closers and subtract to the total grouper.
                elif charlist[char] == groupers[group][1]:
                    groupers[group][2] -= 1
                    break
            # When there is no open group and a comma separate out the command.
            if not(groupers[0][2] or groupers[1][2] or groupers[2][2]) and charlist[char] == ',':
                # Get the most recent command by taking the end of the last command and the current character.
                commandList.append(line[previous:char])
                commandList[-1].strip()
                previous = char+1
        if not commandList:
            return [line]
        else:
            return commandList

    def parseCommand(self, command):
        """
        parseCommand: Looks through the command determines which one it is and executes it.

        Parameter:
        :param command: A singular string command that will compared against the available commands.
        """
        if command == 'endProgram()':
            self.endProgram()
        elif command == 'endCapture()':
            self.endCapture = True
        elif command == 'startSeek()':
            self.startSeek = True
        elif command == 'stopSeek()':
            self.stopSeek = True
        elif command == 'startManagement()':
            self.startManagement = True
        elif command == 'stopManagement()':
            self.stopManagement = True
        elif command == 'startCapture()':
            self.startCapture = True
        elif command == 'stopCapture()':
            self.stopCapture = True
        elif command[:15] == 'startRecording(' and command[-1] == ')':
            try:
                with statsLock:
                    on = self.stats['Is Recording']
                if not on:
                    if command[15:-1]:
                        self.startRecording(startTime=float(command[15:-1]))
                    else:
                        self.startRecording()
                else:
                    print('Already Recording')
            except:
                print('Error: Invalid syntax in ' + command)
        elif command[:14] == 'stopRecording(' and command[-1] == ')':
            try:
                with statsLock:
                    on = self.stats['Is Recording']
                if on:
                    if command[14:-1]:
                        if ',' in command[14:-1]:
                            stopTime, fromStart = re.split(',', command[14:-1])
                            stopTime = float(stopTime.replace(' ', ''))
                            fromStart = re.findall('True|False', fromStart)[0]
                            if fromStart == 'True':
                                fromStart = True
                            else:
                                fromStart = False
                        else:
                            stopTime = command[14:-1]
                            fromStart = False
                        self.stopRecording(stopTime=float(stopTime), fromStart=fromStart)
                    else:
                        self.stopRecording()
                else:
                    print('Already not Recoding')
            except:
                print('Error: Invalid syntax in ' + command)
        elif command == 'printDelay()':
            self.printDelay()
        elif command == 'printFPS()':
            self.printFPS()
        # Changing a Variable
        elif '=' in command:
            param, value = command.split('=')
            param = param.strip()
            value = value.replace(' ', '')
            if param in self.parameters:
                newValue = None
                if value.isnumeric():
                    newValue = int(value)
                else:
                    try:
                        newValue = float(value)
                    except:
                        try:
                            if value == 'True':
                                newValue = True
                            elif value == 'False':
                                newValue = False
                        except:
                            print('Error: '+param+' was assigned to an invalid value!')
                if not type(newValue) == None:
                    self.changedParams.append(param)
                    self.changedParams.append(newValue)
                    self.globalCommands = True
            else:
                print('Error: ' + param + ' name does not exist.')
        else:
            print('Error: ' + command + ' is not a command.')

    def startRecording(self, startTime=None):
        """
        startRecording: Tells the other objects to start recording.

        Parameter:
        :param startTime: The time in seconds when to start recording from when this command executes.
        """
        if startTime:
            startTime += datetime.datetime.now().timestamp()
            with paramLock:
                self.parameters['Sync Time'] = startTime
                self.parameters['Start Record Time'] = startTime-0.125
                self.parameters['Set Start Record'] = True
        else:
            with paramLock:
                self.parameters['Set Start Record'] = False
        startRecording.set()

    def stopRecording(self, stopTime=None, fromStart=False):
        """
        stopRecording: Tells the other objects to stop recording.

        Parameter:
        :param stopTime: The time in seconds when to stop recording from when this command executes.
        :param fromStart: The time in seconds when to stop recording from when recording started.
        """
        if stopTime:
            if fromStart:
                with paramLock:
                    stopTime += self.parameters['Start Record Time']
            else:
                stopTime += datetime.datetime.now().timestamp()
            with paramLock:
                self.parameters['End Record Time'] = stopTime
                self.parameters['Set Stop Record'] = True
        else:
            with paramLock:
                self.parameters['Set Stop Record'] = False
        stopRecording.set()

    def printFPS(self):
        """ printFPS: Prints the FPS."""
        with statsLock:
            fps = self.stats['True Frame Rate']
        print('FPS: {:0.3f}'.format(fps))

    def printDelay(self):
        """ printDelay: Prints the delay between frame capture and the frame being processed"""
        with statsLock:
            rawdelay = self.stats['Raw Frame Delay']*1000
            prodelay = self.stats['Processed Frame Delay']*1000
        print('Raw Frame Delay: {:0.3f} ms'.format(rawdelay))
        print('Processed Frame Delay: {:0.3f} ms'.format(prodelay))

    def endProgram(self):
        """ endProgram: Asks the user if they wish to end the program."""
        command = input('\nDo you wish to end? [y/N] ')
        if command.upper() == 'YES' or command.upper() == 'Y':
            self.endCapture = True
            self.stopRunning = True

    def resetFlags(self):
        """ resetFlags: Reset the flags that this object uses to indicate changes."""
        self.startSeek = False
        self.stopSeek = False
        self.startManagement = False
        self.stopManagement = False
        self.startCapture = False
        self.stopCapture = False
        self.globalCommands = False
        self.endOthers = False


########## Main Program ##########

if __name__ == "__main__":
    # Get Information from commandline
    for arg in sys.argv[1:]:
        print(arg)

    # Setup Objects #
    myCommands = SudoCommandLine(parameters=camParams, stats=returnedData)
    capture = PiCameraCapture(camParams, statsProduced=returnedData)
    manager = FrameManager(statsProduced=returnedData, rawFrameq=capture.frameStreamq)
    manager.processor.processParams = processParams
    communicator = ServerCommunicator(manager, camParams, resetParams, returnedData, standAlone=True)


    # Start Running Processes #
    if quickStart:
        communicator.seeker.startSeeking()
        manager.startManagement()
        capture.startCapture()
    # Program Loop
    while consecutiveRuns or manager.continueRunning.is_set():
        # Clear any flags that might have been active from last loop.
        myCommands.resetFlags()

        # Wait for user input and execute any commands that can be done within myCommands.
        myCommands.userInput()


        # When finished with local commands in myCommands then execute any global commands.
        if myCommands.globalCommands:
            communicator.setParams(tuple(myCommands.changedParams))

        # Seeking Server commands.
        if myCommands.startSeek:
            communicator.seeker.resetSeeking()
        if myCommands.stopSeek:
            communicator.seeker.endSeeking()

        # Management commands.
        if myCommands.startManagement:
            manager.startManagement()
        if myCommands.stopManagement:
            manager.endManagement()

        # Capture commands.
        if myCommands.startCapture:
            capture.startCapture()
        if myCommands.stopCapture:
            capture.endCapture()

        # If endCapture was set then end the capture, server communicator, and server seeker.
        if myCommands.endOthers:
            if capture.continueRunning.is_set() or manager.continueRunning.is_set():
                capture.endCapture()
                if manager.continueRunning.is_set():
                    manager.endManagement()
            if communicator.continueRunning.is_set():
                communicator.endCommunication()
            if communicator.seeker.continueRunning.is_set():
                communicator.seeker.endSeeking()

        # Set whether whole program ends or not.
        consecutiveRuns = not myCommands.stopRunning
