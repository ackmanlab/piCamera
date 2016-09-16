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

Basic Commands:
startSeek(): Starts the SeverSeeker object which tries to find the server designated by the hostname.
stopSeek(): Stops the ServerSeeker object.
startCapture(): Starts the CameraCapture and FrameManager objects.
stopCapture(): Stops the CameraCapture and FrameManager objects.
printFPS(): Print the FPS that is currently being achieved.
printDelay(): Prints the delay of a frame being captured to when it is saved and processed.
printCamParams(): Prints the camera parameters that can be changed.
printProPrams(): Prints the processing parameters that can be changed.
printStats(): Prints the Stats returned by the objects.
printLocks(): Prints the locks used by the objects.
endOthers(): Ends all other objects that have threads. (Communicator, ServerSeeker, CameraCapture, and FrameManager)
endProgram(): Ends the whole program. It will ask if you really want to do that.

Recording Commands:
startRecording([startTime]): Starts recording.
    startTime: A float of the time in seconds when to start recording from when this command executes.

stopRecording([stopTime], [fromStart=False]): Stops recording
    stopTime: A float time in seconds when to stop recording from when this command executes.
    fromStart: A boolean that chooses the stop time from the when this command executes or from the start of the
               recording.

Examples:
To start or stop the recording immediately:
startRecording()
stopRecording()
To set the recording to record for 2 minutes:
startRecording(30)                      # Start the recording in 30s. (Before it starts type the next command.)
stopRecording(60, True)                 # Stop the recording 120s after the recording has started.


Changing Parameters Command:
[Parameter] = [New Value] : Change a camera parameter to a new value. Remember it is case sensitive.

Example:
Filename = Rat_2423                 (Changes the files' names to start with "Rat_2423" and the date will be appended.)
FPS = 25
Set Stop Record = False

Additional Note: If the video files have nothing in them check if the video encoder selected is the issue. Also not all
video players can play back certain encodings but VLC media player can do most. The default codec is Huffman Lossless
Codec(HFYU) which is lossless and not CPU intensive but makes large file sizes.
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
import os
import threading
from queue import Queue
from statistics import mean

# Downloaded Libraries
import numpy
import cv2

# Custom Libraries
import imageProcess
import baseCapture
try:
    import piCapture
except:
    pass


########## Definitions ##########

# Classes #

class USBCameraCapture(baseCapture.CameraCapture):
    def __init__(self,  cameraNumber=0):
        """
        USBCameraCapture: An object that interacts with a USB camera to capture frames.

        Required Modules: datetime, io, queue, threading, cv2
        Required Classes: None
        Methods: startCapture, endCapture, resetCapture, newFile, setDimFPS, waitUntil, mergeLocks, mergeCamParams,
                 mergeReturnedData, __captureTask

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters:
        :param cameraNumber: The number of the camera that the object will use for capture.

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
        resetParams: A list of the parameters that require the camera to reset.
        returnedData: Information produced about the camera such as recoding state and frame rate.
        dimensionLock: A lock to prevent changing the resolution of the frame while the camera is capturing.
        sync: A synchronization event that causes the camera to start when the event is triggered.
        syncRecord: A synchronization event that causes the camera to start and record when the event is triggered.
        record: An event that starts recording.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        captureThread: The thread that sets up capture and creates frames from the camera.
        recorderThread: A thread that controls whether the frames are being recorded/saved.
        """
        # Setup Parent Class Attributes
        super().__init__()

        # Parameters
        self.cameraNumber = cameraNumber

        # Attributes
        self.camParams.update({'X Resolution': 640, 'Y Resolution': 480, 'FPS': 30, 'Expo Comp': 0})
        self.resetParams = ['X Resolution', 'Y Resolution', 'FPS', 'Expo Comp']
        self.captureTask = self.__captureTask
        self.captureThread = threading.Thread(target=self.captureTask)

    # Methods #
    def __captureTask(self):
        """
        __captureTask: A private method that continuously captures frames and puts them into a queue for processing. The
                       method stays in an infinite loop until a different thread clears the continueRunning event.
        """
        # Setup Capture
        self.camera = cv2.VideoCapture(self.cameraNumber)   # Sets the camera that creates the frames
        while self.continueRunning.is_set():
            self.locks['stopFrameCap'].clear()              # Clear the stop capture event.
            self.frameNumber = 0                            # Clear the frame numbering system.

            with self.locks['paramLock']:
                self.camera.set(3, self.camParams['X Resolution'])
                self.camera.set(4, self.camParams['Y Resolution'])
                self.camera.set(5, self.camParams['FPS'])
                self.camera.set(15, self.camParams['Expo Comp'])
                self.setDimFPS(self.camParams['X Resolution'], self.camParams['Y Resolution'],
                               self.camParams['FPS'])
                # Set a synchronization time to start the capture time at.
                synctime = self.camParams['Sync Time']

            # Setup the Capture Timing
            if self.syncRecord.is_set():                    # If recording at sync time then:
                self.syncRecord.clear()                     # Reset sync recording for next time.
                self.record.set()                           # Set to record immediately when capturing.
                print('Recording ' + self.fileList[-1])     # Notify recording the new file.
                self.waitUntil(synctime)                    # Wait until sync time.
            elif self.sync.is_set():                        # When synchronizing capture times then:
                self.sync.clear()                           # Clear sync for next time.
                self.waitUntil(synctime)                    # Wait until sync time.

            # Set up the infinite capture loop.
            while (not self.locks['stopFrameCap'].is_set()) and self.continueRunning.is_set():
                ret, img = self.camera.read()
                self.frameNumber += 1                       # When done increase the number of frames captured
                # Put the frame on the queue with its information. The are some unsafe interactions for speed, be careful!
                # [Frame, width, height, FPS, frame number, current time, filename to save as, whether to save or not]
                self.frameStreamq.put([img, self.width, self.height, self.fps,
                                       self.frameNumber, time.time(), self.fileList[-1], self.record.is_set()])
        # When finished release the camera.
        self.camera.release()


class FrameManager:
    def __init__(self, frameType='jpeg', clientSocket=None, rawFrameq=Queue(), rawThreadCount=1, directory=os.getcwd()):
        """
        FrameManager: An object that accepts frames, processes them, and saves them.

        Required Modules: queue, threading, imageProcess
        Required Classes: ImageConverter, SavingThread, ImageProcess, ImageProcessor, ImageStreamer
        Methods: startManagement, endManagement, restartManagement, findAverageTime, connect2Server, mergeLocks,
                 mergeCamParam, mergeReturnedData, mergeProcessParams, __getRawTask, __copyProTask, __statsTask

        Class Attributes
        none:

        Object Parameters & Attributes
        Parameters:
        :param frameType: The encoding of the raw frames.
        :param clientSocket: An optional socket to stream processed frames to.
        :param rawFrameq: A queue where the raw frames are being supplied.
        :param rawThreadCount: The number of threads converting the raw frame into an open CV object.
        :param directory: The directory to store the produced files in.

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
        locks: The threading locks used by this object.
        returnedData: A dictionary of the statistics produced by the frame manager.
        processParams: A dictionary of the parameters needed for processing a frame.
        rawThreadCount: The number of threads used to prepare raw frames to be saved and processed.
        continueRunning: An event that tells all the threads to stay alive and shutdown.
        getRawThreadList: A list of threads used tp prepare raw frames to be saved and processed.
        proCopyThread: A thread that prepares processed frames to be saved and streamed.
        statsThread: A thread used to collect the statics on the frame management process.
        """
        # Parameters
        self.clientSocket = clientSocket
        self.rawFrameq = rawFrameq

        # Attributes
        self.statsq = Queue()
        # Objects
        self.frameConverter = ImageConverter(frameType, 'BGR')
        self.rawSaver = SavingThread('video', directory=directory)
        self.processedSaver = SavingThread('video', directory=directory)
        self.timestampSaver = SavingThread('timestamp', directory=directory)
        self.processInfoSaver = SavingThread('processinfo', directory=directory)
        self.imageProcess = imageProcess.ImageProcess()
        self.processor = ImageProcessor(self.imageProcess.blankProcess, threadCount=2)
        if clientSocket:                                    # Create a VideoStreamer object if there was a socket.
            self.streamer = VideoStreamer(clientSocket, threadCount=2)
        else:
            self.streamer = None
        # Threads
        self.locks = {'statsLock': threading.Lock(), 'connection_lock': threading.Lock(),
                      'sendFrames': threading.Event()}
        self.returnedData = {'True Frame Rate': 0, 'Raw Frame Delay': 0, 'Processed Frame Delay':0}
        self.camParams = {'FPS': 30}
        self.processParams = self.imageProcess.parameters
        self.continueRunning = threading.Event()
        self.rawThreadCount = rawThreadCount
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
        self.getRawThreadList.clear()

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
        # End Stats Thread.
        self.statsq.put(None)
        self.statsThread.join()

        # End streaming thread if it exists
        if self.clientSocket:
            self.streamer.endStreaming()
            with self.locks['connection_lock']:
                self.clientSocket.write(struct.pack('<L', 0))   # Tell the server we are done streaming.
        print('Frame Management Ended')             # Print that the manager has shutdown.

    def resetManagement(self, clientSocket=None):
        """
        resetCapture: Restart the capture from an ended state and optionally change some parameters.

        Parameters:
        :param clientSocket: The socket to connect the streamer to.
        """
        if not self.continueRunning.is_set():           # When not running or shutting down:
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
            for worker in range(self.rawThreadCount):  # Create the number of raw manager threads.
                self.getRawThreadList.append(threading.Thread(target=self.__getRawTask))
            self.proCopyThread = threading.Thread(target=self.__copyProTask)
            self.statsThread = threading.Thread(target=self.__statsTask)
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

    def findSlope(self, xs, ys):
        m = (mean(xs)*mean(ys)-mean(xs*ys))/(mean(xs)**2-mean(xs**2))
        return m

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

    def mergeProcessParams(self, master):
        """
        mergeProcessParams: Merges the image process parameters into a master dictionary and uses that instead.

        Parameters:
        :param master: The master dictionary where the camera parameters will be stored.
        """
        for key, value in self.processParams.items():
            if key not in master:
                master[key] = value
        self.processParams = master

    def __getRawTask(self):
        """
        __getRawTask: A thread task that takes a frame and its information from the raw frame queue and prepares it to
                     be saved and processed.
        """
        while self.continueRunning.is_set():            # Keep the thread running while true.
            # Get a raw frame and its information from the raw frame queue.
            frameStream, width, height, fps, frameNumber, timestamp, file, save = self.rawFrameq.get()
            # If it was something then do this:  (Since .get() is blocking, Nones are loaded into the queue to unblock)
            if frameStream is not None:
                # If the frame stream is a buffer "get" it.
                if isinstance(frameStream, type(io.BytesIO())):
                    frameStream = frameStream.getbuffer()
                # Convert the frame from a certain type to an OpenCV object, an BGR file.
                frameBGR = self.frameConverter.convert(frameStream, width, height)
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
                # frameStream.close()                     # Close the bytestream object to free up memory.
                # Send statistical information to the stats thread via queue.
                self.statsq.put(['Raw', frameNumber, time.time(), timestamp])
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
                if self.locks['sendFrames'].is_set() and self.streamer:
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
                self.statsq.put(['Pro', frameNumber, time.time(), timestamp])

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
                    rawTimes.append([stats[1], stats[2], stats[2]-stats[3]])
                    # Put raw FPS information into a list with:
                    # [frame number, time of frame capture]
                    trueFPS.append([stats[1], stats[3]])
                else:                                               # If from processed frame:
                    # Put processed timestamp information into a list with:
                    # [frame number, time finishing pro management, delay from capture to finishing pro management]
                    proTimes.append([stats[1], stats[2], stats[2]-stats[3]])

                # Every now and then calculate FPS and delay.
                if time.time() > start:                             # Once 10 seconds have passed:
                    with self.locks['paramLock']:
                        fps = self.camParams['FPS']
                    # Sort the timestamps by frame order.
                    trueFPS.sort(key=lambda times: times[0])
                    rawTimes.sort(key=lambda times: times[0])
                    proTimes.sort(key=lambda times: times[0])

                    # Calculate FPS if there is more than one frame timestamp.
                    if len(trueFPS) > 1:
                        averfps = self.findAverageTime(trueFPS, delay=False)
                    # Check if the FPS is correct.
                    if averfps < averfps-2:
                        print('WARNING: True FPS is {:}fps which is lower than expected!'.format(averfps))
                    elif averfps > fps+5:
                        print('WARNING: True FPS is {:}fps which is higher than expected!'.format(averfps))
                    # Check if the Delays are stable.
                    if len(rawTimes) > 1:
                        rawFrameTotal = numpy.array([x for x in range(len(rawTimes))], dtype=numpy.float64)
                        rawDelays = numpy.array([rawTimes[y][2]*1000 for y in range(len(rawTimes))], dtype=numpy.float64)
                        averRawDelay = mean(rawDelays)
                        rawSlope = self.findSlope(rawFrameTotal, rawDelays)*averfps
                        if rawSlope > 0.1:
                            print('WARNING: Raw Delay is Increasing! This can FREEZE The COMPUTER if left unchecked.')
                            print('Increase: {:0.6f} ms/s'.format(rawSlope))
                    if len(proTimes) > 1:
                        proFrameTotal = numpy.array([x for x in range(len(proTimes))], dtype=numpy.float64)
                        proDelays = numpy.array([proTimes[y][2]*1000 for y in range(len(proTimes))], dtype=numpy.float64)
                        averProDelay = mean(proDelays)
                        proSlope = self.findSlope(proFrameTotal, proDelays)*averfps
                        if proSlope > 0.1:
                            print('WARNING: Processed Delay is Increasing! This can cause COMPUTER FAILURE if left unchecked.')
                            print('Increase: {:0.6f} ms/s'.format(proSlope))
                    # Safely updated the statistics for other threads to see.
                    with self.locks['statsLock']:
                        self.returnedData['True Frame Rate'] = averfps
                        self.returnedData['Raw Frame Delay'] = averRawDelay
                        self.returnedData['Processed Frame Delay'] = averProDelay
                    trueFPS.clear()
                    rawTimes.clear()
                    proTimes.clear()
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
        # conversionTable:       BRG                YUV           JPEG
        self.conversionTable = [[self.noChange,    None,          None],
                                [self.yuv420p2bgr, self.noChange, None],
                                [self.jpeg2bgr,    None,          self.noChange]]
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
        if previous.upper() == 'BGR':
            self.row = 0
        elif previous.upper() == 'YUV420':
            self.row = 1
        elif previous.upper() == 'JPEG':
            self.row = 2
        else:
            raise RuntimeError('Cannot convert from a ' + previous + ' type.')

        # Determine if the new image type is an available type and get its index.
        if new.upper() == 'BGR':
            self.column = 0
        elif new.upper() == 'YUV420':
            self.column = 1
        elif new.upper() == 'JPEG':
            self.column = 2
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

    def noChange(self, frameBuffer, width, height):
        """
        noChange: Returns the frame.

        Parameters:
        :param frameBuffer: The buffer that contains the image.
        :param width: The width of the image in pixels.
        :param height: The height of the image in pixels.
        :return: A BGR numpy array of the frame.
        """
        return frameBuffer

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
    def __init__(self, type='video', fileFormat=None, encoder=None, directory=None):
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
        :param encoder: The encoder used to save videos with the default is Huffman Lossless Codec(HFYU).
        :param directory: The directory to save the files in.

        Attributes:
        frameSaveq: The queue where to get the incoming information that will be saved.
        continueRunning: A singal that keeps the saving thread alive.
        """
        # Parameters
        self.saveType = type
        if dir:
            try:
                os.chdir(directory)
                self.directory = directory
            except:
                self.directory = os.getcwd()
                print('Error: Invalid directory using {:}'.format(self.directory))
        else:
            self.directory = directory
        # Use the strings from the parameters to choose the file format and encoder.
        self.fileFormat, self.encoder = self._get_save_type(type, fileFormat, encoder)
        # Attributes
        self.currentVideo = None
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
                self.fileFormat, self.encoder = self._get_save_type(self.saveType, fileFormat, encoder)
            else:
                _ = self._get_save_type(self.saveType, fileFormat, encoder)
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
            encoder = tuple(ccFormat for ccFormat in (encoder or 'HFYU'))       # Choose the video encoder.
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
                    if self.currentVideo:                               # Release file if there is one present.
                        self.currentVideo.release()
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
        # When shutting down release the last file.
        if self.currentVideo:
            self.currentVideo.release()

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
                dataSheet.write(self.lineText.format(frameNumber, datetime.datetime.fromtimestamp(timestamp)))
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
                        timestamp = datetime.datetime.fromtimestamp(timestamp)  # Change it to datetime form.
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
                        break
        self.frameSaveq.task_done()

    def __saveProcessInfoTask(self):
        """ __saveTimestampsTask: A thread task that takes frame timestamps from the queue and saves it to a file."""
        holdFrames = []                                                     # A list of frames to temporarily hold out of order frames.
        # Get the first set of information.
        information, width, height, frameNumber, timestamp, file = self.frameSaveq.get()
        while self.continueRunning.is_set():                                # Continuously wait for a information to save.
            with open(file + self.fileFormat, 'w') as dataSheet:            # Open or create a text file.
                # Write the information to the file.
                dataSheet.write(self.fileHeader)
                dataSheet.write(self.subHeader.format(frameNumber, datetime.datetime.fromtimestamp(timestamp)))
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
                        timestamp = datetime.datetime.fromtimestamp(timestamp)  # Change time to datetime form.
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
                        break
        self.frameSaveq.task_done()


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
        if len(self.threadList):
            for worker in range(self.threadCount):          # For all threads:
                if self.threadList[worker].is_alive():      # If there is a thread in list that is alive:
                    return True                             # Return true.
        return False                                        # If all threads are dead then return false.

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
        self.threadList.clear()

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
            for worker in range(self.threadCount):
                self.threadList.append(threading.Thread(target=self.__processingTask))
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
                results = self.function(data)      # Process that data with self.function.
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
        self.locks = {'connection_lock': threading.Lock()}
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
        with self.locks['connection_lock']:                   # Safely access the client socket.
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
        self.threadList.clear()

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
            for worker in range(self.threadCount):
                self.threadList.append(threading.Thread(target=self.__streamingTask))
            for worker in range(self.threadCount):          # Start the streaming threads.
                self.threadList[worker].start()
            print('Streaming to {:} has restarted'.format(self.clientSocket))  # Print we have started streaming.
        else:                                               # If the threads were on then print we have failed.
            print('Reset Failed: Close Down Streaming Before Resetting!')

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

    def __streamingTask(self):
        """ __streamingTask: A thread task that takes frames and streams them."""
        while self.continueRunning.is_set():                    # Continuously wait for a information to stream.
            frameBGRnpa, frameNumber = self.sendFrameq.get()    # Get data from to be frame queue.
            if frameBGRnpa:                                     # If there was data:
                stream = io.BytesIO(frameBGRnpa)                # Turn the data into a byte stream.
                try:                                            # Try to send data:
                    with self.locks['connection_lock']:         # When socket is available:
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
        self.locks = {'paramLock': threading.Lock(), 'statsLock': threading.Lock(),
                      'startRecording': threading.Event(), 'stopRecording': threading.Event(),
                      'dataReceived': threading.Event(), 'stopFrameCap': threading.Event(),
                      'sendFrames': threading.Event(), 'sendServerData': threading.Event()}
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
        self.locks['sendServerData'].set()
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
            self.receivingThread = threading.Thread(target=self.__receivingTask)
            self.sendingThread = threading.Thread(target=self.__sendTask)
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
                    self.locks['sendFrames'].set()
                else:
                    self.locks['sendFrames'].clear()
            elif info[index] == 'Meter Mode' or info[index] == 'Expo Mode':
                # Meter mode and Expo mode need to be decoded some more.
                info[index + 1] = self.decodeParams(info[index], info[index + 1])
            with self.locks['paramLock']:
                self.camParams[info[index]] = info[index + 1]
            if info[index] in self.resetParams:
                reset = True
        # Reset the capture if told to.
        if reset:
            self.locks['stopFrameCap'].set()
        # Start or Stop the recording if told to.
        if record:
            if begin:
                self.locks['startRecording'].set()
            else:
                self.locks['stopRecording'].set()

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
                self.locks['dataReceived'].set()                   # Tell other threads there was data received.

    def __sendTask(self):
        """ __sendTask: A thread task that sends information across the socket for the server take."""
        toEcode = []                                                    # Message to fill and send.
        while self.continueSending.is_set():                            # Continuously send messages from server.
            toEcode.clear()                                             # Remove extra data.
            time.sleep(self.sendDelay)                                  # Wait to send information the server.
            # Create a message to send
            with self.locks['statsLock']:                               # Safely get statistics to send to server.
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
        print('Server Seeking Ended')

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
            self.seekingThread = threading.Thread(target=self.__seekServerTask)
            self.seekingThread.start()
            print('Seeking has begun again.')
        else:
            print('Reset Failed: Shutdown Seeking Before Resetting!')

    def __seekServerTask(self):
        """ __seekServerTask: A thread task that seeks a server."""
        foundServer = False
        # If there is a socket with a connection already then close it.
        if self.clientConFile:
            self.clientConFile.close()
            self.clientSocket.close()
        # Seek a Server
        while self.continueRunning.is_set():                    # Continuously seek a server.
            try:
                self.clientSocket.connect(self.hostPort)        # Connect to server.
                foundServer = True                              # Note we found a server
                self.continueRunning.clear()                    # Stop seeking because we found a server.
            except:                                             # Timeout may occur.
                continue                                        # Retry seeking.
        # When a server is found create file like object to write to and have the other objects connect to them.
        if foundServer:
            self.clientConFile = self.clientSocket.makefile('wb')
            self.communicator.resetCommunications(clientSocket=self.clientSocket)
            self.manager.connect2Server(self.clientConFile)


class SudoCommandLine:
    def __init__(self,  camParams=None, processParams=None, stats=None):
        """
        ServerSeeker: A threaded object that continuously tries to find a server.

        Required Modules: threading, socket
        Required Classes: None
        Methods:

        Class Attributes
        none

        Object Parameters & Attributes
        Parameters
        :param camParams: Dictionary of the camera parameters used by other objects.
        :param processParams: Dictionary of the processing parameters used by other objects.
        :param stats: Dictionary of the statistics produced by other objects.

        Attributes
        changedParams: List of camera parameters changed by the user.
        changedParams: List of processing parameters changed by the user.
        commands: List of constructors and commands in the the object.
        #Flags
        globalCommands: Boolean if a command entered was a global command.
        startSeek: Boolean if a command entered was start seeking a server.
        stopSeek: Boolean if a command entered was stop seeking a server.
        stopRunning: Boolean if a command entered was stop running the program.
        endCapture: Boolean if a command entered was stop all other objects.
        """
        # Parameters
        self.camParams = camParams
        self.processPrams = processParams
        self.stats = stats
        # Attributes
        self.locks = {'paramLock': threading.Lock(), 'statsLock': threading.Lock(), 'connection_lock': threading.Lock(),
         'startRecording': threading.Event(), 'stopRecording': threading.Event(), 'dataReceived': threading.Event(),
         'stopFrameCap': threading.Event(), 'sendFrames': threading.Event(), 'sendServerData': threading.Event()}
        self.changedParams = []
        self.changedProParams = []
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

    # Methods
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

    def userInput(self):
        """ userInput: Waits for user input and executes commands based on what was entered."""
        self.changedParams.clear()
        # Wait for user input
        #print('Enter Command: ')
        line = input('\nEnter Command: \n')
        #for line in sys.stdin:
        try:
            # Clean up inputted commands
            line = ''.join(line.splitlines()).strip()
            if not line == '':
                commandList = self.splitParenthesis(line)
                # Go through inputs and check if they were commands.
                for command in commandList:
                    self.parseCommand(command)
                # Once finished stop waiting an exit user input.
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
        elif command == 'endOthers()':
            self.endOthers = True
        elif command[:15] == 'startRecording(' and command[-1] == ')':
            try:
                with self.locks['statsLock']:
                    on = self.stats['Is Recording']
                if not on:
                    if command[15:-1]:
                        args = command[15:-1].replace(' ', '').replace('startTime=', '')
                        if args.isnumeric():
                            self.startRecording(startTime=int(args))
                        else:
                            self.startRecording(startTime=float(args))
                    else:
                        self.startRecording()
                else:
                    print('Already Recording')
            except:
                print('Error: Invalid syntax in ' + command)
        elif command[:14] == 'stopRecording(' and command[-1] == ')':
            try:
                if not self.locks['stopRecording'].is_set():
                    if command[14:-1]:
                        if ',' in command[14:-1]:
                            stopTime, fromStart = command[14:-1].split(',')
                            stopTime = stopTime.replace(' ', '').replace('stopTime=', '')
                            if stopTime.isnumeric():
                                stopTime = int(stopTime)
                            else:
                                stopTime = float(stopTime)
                            fromStart = fromStart.replace(' ', '').replace('fromStart=', '')
                            if fromStart == 'True':
                                fromStart = True
                            elif fromStart == 'False':
                                fromStart = False
                            else:
                                print('Error: fromStart was not a Boolean, defaulting to False.')
                        else:
                            stopTime = command[14:-1].replace(' ', '').replace('stopTime=', '')
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
        elif command == 'printCamParams()':
            print(self.camParams)
        elif command == 'printProParams()':
            print(self.processPrams)
        elif command == 'printStats()':
            print(self.stats)
        elif command == 'printLocks()':
            print(self.locks)
        # Changing a Variable
        elif '=' in command:
            param, value = command.split('=')
            param = param.strip()
            value = value.strip()
            if param in self.camParams and not self.stats['Is Recording']:
                newValue = None
                with self.locks['paramLock']:
                    oldValue = self.camParams[param]
                if isinstance(oldValue, int) and value.isnumeric():
                    try:
                        newValue = int(value)
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, int) or isinstance(oldValue, float):
                    try:
                        newValue = float(value)
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, bool):
                    try:
                        if value == 'True':
                            newValue = True
                        elif value == 'False':
                            newValue = False
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, str):
                    value = value.strip('"').strip("'")
                    newValue = value
                else:
                    print('The previous value was not a string, boolean, int, or float. So nothing was changed.')
                if not type(newValue) == None:
                    self.changedParams.append(param)
                    self.changedParams.append(newValue)
                    self.globalCommands = True
            if param in self.processPrams and not self.stats['Is Recording']:
                newValue = None
                with self.locks['paramLock']:
                    oldValue = self.processPrams[param]
                if isinstance(oldValue, int) and value.isnumeric():
                    try:
                        newValue = int(value)
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, int) or isinstance(oldValue, float):
                    try:
                        newValue = float(value)
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, bool):
                    try:
                        if value == 'True':
                            newValue = True
                        elif value == 'False':
                            newValue = False
                    except:
                        print('Error: ' + param + ' was assigned to an invalid value!')
                elif isinstance(oldValue, str):
                    value = value.strip('"').strip("'")
                    newValue = value
                else:
                    print('The previous value was not a string, boolean, int, or float. So nothing was changed.')
                if not type(newValue) == None:
                    self.processPrams[param] = newValue
            elif self.stats['Is Recording']:
                print('Stop Recording Before Changing Parameters!')
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
            startTime += time.time()
            with self.locks['paramLock']:
                self.parameters['Sync Time'] = startTime
                self.parameters['Start Record Time'] = startTime-0.125
                self.parameters['Set Start Record'] = True
        else:
            with self.locks['paramLock']:
                self.parameters['Set Start Record'] = False
        self.locks['startRecording'].set()

    def stopRecording(self, stopTime=None, fromStart=False):
        """
        stopRecording: Tells the other objects to stop recording.

        Parameter:
        :param stopTime: The time in seconds when to stop recording from when this command executes.
        :param fromStart: The time in seconds when to stop recording from when recording started.
        """
        if stopTime:
            if fromStart:
                with self.locks['paramLock']:
                    stopTime += self.parameters['Start Record Time']
            else:
                stopTime += time.time()
            with self.locks['paramLock']:
                self.parameters['End Record Time'] = stopTime
                self.parameters['Set Stop Record'] = True
        else:
            with self.locks['paramLock']:
                self.parameters['Set Stop Record'] = False
        self.locks['stopRecording'].set()

    def printFPS(self):
        """ printFPS: Prints the FPS."""
        with self.locks['statsLock']:
            fps = self.stats['True Frame Rate']
        print('FPS: {:0.3f}'.format(fps))

    def printDelay(self):
        """ printDelay: Prints the delay between frame capture and the frame being processed"""
        with self.locks['statsLock']:
            rawdelay = self.stats['Raw Frame Delay']
            prodelay = self.stats['Processed Frame Delay']
        print('Raw Frame Delay: {:0.3f} ms'.format(rawdelay))
        print('Processed Frame Delay: {:0.3f} ms'.format(prodelay))

    def endProgram(self):
        """ endProgram: Asks the user if they wish to end the program."""
        command = input('\nDo you wish to end? [y/N] ')
        if command.upper() == 'YES' or command.upper() == 'Y':
            self.endOthers = True
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

    # Variables #
    consecutiveRuns = True
    quickStart = True
    storageDirectory = os.getcwd()                      # Put the path to the directory to save the files in.
    hostPort = ('192.168.0.112', 5555)                  # Find the IP of the server and put it here.

    # Setup Objects #
    # Here assign the correct object to object either being a USB camera or a Pi Camera. Uncomment the one desired.
    capture = piCapture.PiCameraCapture(frameType='jpeg')
    #capture = USBCameraCapture(cameraNumber=1)

    manager = FrameManager(frameType='bgr', rawFrameq=capture.frameStreamq, rawThreadCount=4, directory=storageDirectory)
    returnedData = capture.returnedData
    manager.mergeReturnedData(returnedData)

    communicator = ServerCommunicator(manager, capture.camParams, capture.resetParams, returnedData, standAlone=True)
    myCommands = SudoCommandLine(camParams=capture.camParams, processParams=manager.processParams, stats=returnedData)

    masterLock = capture.locks
    myCommands.mergeLocks(masterLock)
    manager.mergeLocks(masterLock)
    communicator.mergeLocks(masterLock)

    # Optional Stuff:
    # Right now the only way to change the header text in the files is by changing it in the object definition or below
    # This means that it can not be changed during run time. It is relatively easy to add this feature but I do not
    # know what should go into the header so I leave it up to someone else to program.
    manager.timestampSaver.fileHeader = 'Type here to add a header to the timestamp file.'
    manager.processInfoSaver.fileHeader = 'Type here to add a header to the processed information file.'
    manager.processInfoSaver.subHeader = 'Type here to add a sub-header to the processed information file.'


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
            myCommands.changedParams.clear()

        # Seeking Server commands.
        if myCommands.startSeek:
            communicator.seeker.resetSeeking()
        if myCommands.stopSeek:
            communicator.seeker.endSeeking()

        # Management commands.
        if myCommands.startManagement:
            manager.resetManagement()
        if myCommands.stopManagement:
            manager.endManagement()

        # Capture commands.
        if myCommands.startCapture:
            manager.resetManagement()
            capture.resetCapture()
        if myCommands.stopCapture:
            capture.endCapture()

        # If endCapture was set then end the capture, server communicator, and server seeker.
        if myCommands.endOthers:
            if capture.continueRunning.is_set() or manager.continueRunning.is_set():
                if capture.continueRunning.is_set():
                    capture.endCapture()
                if manager.continueRunning.is_set():
                    manager.endManagement()
            if communicator.continueRunning.is_set():
                communicator.endCommunication()
            if communicator.seeker.continueRunning.is_set():
                communicator.seeker.endSeeking()

        # Set whether whole program ends or not.
        consecutiveRuns = not myCommands.stopRunning
    print('Entire Program Shutdown')
