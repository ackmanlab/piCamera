#!/usr/bin/env python3
"""
imageProcess.py

Last Edited: 8/9/2016

Lead Author[s]: Anthony Fong
Contributor[s]:

Description:
A library of objects and functions that are algorithms to process raw frames from a cameras. These are singular
processes that are not multi-threaded but are designed to work with threading and can be apart of threads.

Machine I/O
input: none
output: none

User I/O
input: none
output: none

Tips:
In ImageProcess the parameters dictionary acts as an interface of data between threads and/or objects. It is best
thought as sub-space to store names/variables that can be changed by any scope that can access it. Access is when the
reference is passed to that scope. However, be careful when programing with multi-threading because if there are threads
writing to the parameters while another thread is accessing them can cause errors. Design the functions so there
are no possibility for threads to write and access at the same time or use threading locks.

Also assign the parameters locally at beginning of the function with the lock. Similarly at the end of the function if
needed change the parameters with a lock statement.
Example: Calling a parameter from dictionary
    contrast = self.parameters['Contrast']

For more information on dictionaries check the dictionary documentation at:
https://docs.python.org/3/library/stdtypes.html#typesmapping

There are multiple functions within ImageProcess and act as different methods of processing images. At the very bottom
of ImageProcess is the function __imageProcess0 but rather than acting as a function it acts as template for future
functions. Simple copy and paste it in ImageProcess, fill in the blank area with an algorithm, and change the name &
description (remove the double underscore on the new function since it will be public function). Afterwards make sure
any programs using this library are updated accordingly.
"""
###############################################################################


########## Librarys, Imports, & Setup ##########

# Default Libraries
import threading

# Downloaded Libraries
import numpy
import cv2

########## Definitions ##########


class ImageProcess:
    def __init__(self):
        """ ImageProcess:
                An object that defines how a frame will be processed.
                Required Modules: numpy, cv2
                Required Classes: None
                Parameters: parameters
                Methods: changeParams, imageProcess1, imageProcess2

            Class Attributes
            none

            Object Parameters & Attributes
            Parameters
            :param parameters: A dictionary containing essential parameters and values for processing images.

            Attributes
            paramsLock: A lock for the parameters to prevent data corruption.
        """
        self.parameters = {'Parameters': 'values'}
        self.paramsLock = threading.Lock

    # Methods #
    def changeParams(self, parameters):
        """
        changeParams: Change the dictionary referencing to a copy of another.

        Parameter
        :param parameters: The new dictionary of parameters to reference.
        """
        with self.paramsLock:
            self.parameters = parameters.copy()

    def blankProcess(self, data):
        """
        blankProcess: A process that does nothing but pass the information.

        Parameters
        :param data: The frame and its details to process.
        data format: [frameBGRnpa, width, height, fps, frameNumber, timestamp, file, save]
            frameBGRnpa: The raw frame.
            width, height, fps, frameNumber, timestamp: Information about the frame. Do not change.
            file, save: Filename and a boolean whether this frame will be saved. Do not change.
        :return results:
        results format: [proFrameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save]
            proFrameBGRnpa: The frame with alterations done to it.
            width, height, fps, frameNumber, timestamp: Information about the frame. Do not change.
            information: Bit encoded information that was obtained from the processing.
            file, save: Filename and a boolean whether this frame will be saved. Do not change.
        """
        # Separate out the data.
        frameBGRnpa, width, height, fps, frameNumber, timestamp, file, save = data
        ## No Image Processing ##
        # Pass information to return.
        proFrameBGRnpa = frameBGRnpa
        information = b'None'
        # Create format to return the information as.
        results = [proFrameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save]
        return results

    def __imageProcess0(self, data):
        """
        __imageProcess0: A template for new processes. [Change the name and the description when this function has content.]

        Parameters
        :param data: The frame and its details to process.
        data format: [frameBGRnpa, width, height, fps, frameNumber, timestamp, file, save]
            frameBGRnpa: The raw frame.
            width, height, fps, frameNumber, timestamp: Information about the frame. Do not change.
            file, save: Filename and a boolean whether this frame will be saved. Do not change.
        :return results:
        results format: [proFrameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save]
            proFrameBGRnpa: The frame with alterations done to it.
            width, height, fps, frameNumber, timestamp: Information about the frame. Do not change.
            information: Bit encoded information that was obtained from the processing.
            file, save: Filename and a boolean whether this frame will be saved. Do not change.
        """
        # Separate out the data.
        frameBGRnpa, width, height, fps, frameNumber, timestamp, file, save = data

        ## Parameter Retrieval ##
        with self.paramsLock:
            param = self.parameters['Parameters']   # An example replace with something more apt.

        ## Image Processing ##



        proFrameBGRnpa = frameBGRnpa
        information = b'Something interesting goes here.'
        # Create format to return the information as.
        results = [proFrameBGRnpa, width, height, fps, frameNumber, timestamp, information, file, save]
        return results