#!/usr/bin/env python3
'''
To be used on the MASTER Raspberry Pi to regulate capture speeds.  

This will send TTL pulses to a variety of devices to ensure syncronous recording.

ASSUMPTION: all used rates (fps and events per second) need to be an integer factor
            of the fastest rate.:
        
        i.e.: picamera fps:30, cmos fps:10, stim events per sec: 0.1
                cmos would be triggered every 3rd iteration (30/10), defined by picamera
                stim would be triggered every 300th iteration (30/0.1), defined by the picamera
            i.e.: picamera fps:25, cmos fps:10, stim events per sec: 0.1
                cmos CANNOT be triggered every 2.5th iteration (25/10), defined by picamera
                stim would be triggered every 250th iteration (25/0.1), defined by the picamera
'''

import pigpio
from timeit import default_timer as timer
import numpy as np
import time
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("-l", "--length", type = float, default = 1,
                help="desired video length in minutes")
ap.add_argument("-pl", "--precedinglength", type = float, default = 0,
                help="desired length of video before recording the braindata in minutes")
ap.add_argument("-fc", "--fcmos", type = float, default = 10,
                help="cMOS camera frequency (frames per second)")
ap.add_argument("-fp", "--fpi", type=float, default=30,
                help="pi camera frequency (frames per second)")
ap.add_argument("-fs", "--fstim", type=float, default = None, required = False,
                help="stimulation frquency (events per second)")
args = vars(ap.parse_args())

#intial parameters for camera rates
fpscMOS = args['fcmos'] #fps for cMOS camera
fpspi = args['fpi'] #fps for USB camera
mlen = args['length'] # in minutes
timesec = mlen * 60
bodyonlytime = args['precedinglength'] * 60
lag = 0 #0.0002

print('Total length of body video cam: ' + str(timesec + bodyonlytime) + ' sec()')
print('Total length of brain video cam: ' + str(timesec) + ' sec(s)')

#calculating looping parameters
if fpscMOS >= fpspi:
    nframe = timesec * fpscMOS #(min * 60sec/min * fps)
    step = 1. / fpscMOS + lag
    fac = fpscMOS / fpspi
if fpscMOS < fpspi:
    nframe = timesec * fpspi
    step = 1. / fpspi + lag
    fac = fpspi / fpscMOS

if args['fstim'] is not None:
    if fpscMOS >= fpspi:
        stim_fac = np.around(fpscMOS / args['fstim'])
    if fpscMOS < fpspi:
        stim_fac =  np.around(fpspi / args['fstim'])

ran = np.arange(0, (mlen * 60) + step, step)
#ran = np.arange(0, 10 + step, step)

#initialize handles for TTL and UDP
pi = pigpio.pi() #TTL

#TTL write
def pulse(GPIO, dur):
    pi.write(GPIO, 1) # high
    time.sleep(dur) # in sec
    pi.write(GPIO, 0) # low

def pulseAll(GPIOlist, dur):
    t0 = timer()
    for i, pin in enumerate(GPIOlist):
        pi.write(pin, 1) # high
    
    dursleep = dur - 2*(timer() - t0)
    if dursleep >= 0:
        time.sleep(dursleep)
    
    for i, pin in enumerate(GPIOlist):
        pi.write(pin, 0) # low

camAquire = 10  
led1Blue = 23  
led2Blue = 12  
led3IR = 13  
led4IR  = 26  
piCam1 = 5  
piCam2 = 4  
cMOS = 24  
stimulation = 10

print('Warming up lights')
pi.write(led3IR, 1)
pi.write(led4IR, 1)
time.sleep(5)

t0 = timer()
print('Triggering camera start')
for i in range(5):
    pulse(cMOS, 0.01)
    pulse(piCam2, 0.01)

time.sleep(bodyonlytime)
print('Bod cam only ' + str(timer() - t0))

print('Turning on lights and triggering cMOS camera')
#for loop sending information
t1 = timer()
pi.write(camAquire, 1) # Cam Aquire
pi.write(led1Blue, 1)
pi.write(led2Blue, 1)
try:
    j = 1
    for i, n in enumerate(ran[:-1]):
        #send TTL
        if args["fstim"] is not None:
            if ((i%(fac)) == 0) and ((i%(stim_fac)) == 0):
                pulseAll([cMOS, stimulation], 0.005) # Trigger for aquisition
                tsleep = ran[i+j] - (timer() - t0)
                if tsleep >= 0:
                    time.sleep(tsleep)
                else:
                    j+=1
                    print('Dropped frame')
            elif (i%(fac)) == 0:
                pulse(cMOS, 0.005) # Trigger for aquisition
                tsleep = ran[i+j] - (timer() - t0)
                if tsleep >= 0:
                    time.sleep(tsleep)
                else:
                    j+=1
                    print('Dropped frame')

        else:
            if (i%(fac)) == 0:
                pulse(cMOS, 0.005) # Trigger for aquisition
                tsleep = ran[i+j] - (timer() - t0)
                if tsleep >= 0:
                    time.sleep(tsleep)
                else:
                    j+=1
                    print('Dropped frame')

    # j = 1
    # for i, n in enumerate(ran[:-1]):
    #     #send TTL
    #     if args["fstim"] is not None:
    #         if ((i%(fac)) == 0) and ((i%(stim_fac)) == 0):
    #             pulseAll([piCam1, piCam2, cMOS, stimulation], 0.005) # Trigger for aquisition
    #             tsleep = ran[i+j] - (timer() - t0)
    #             if tsleep >= 0:
    #                 time.sleep(tsleep)
    #             else:
    #                 j+=1
    #                 print('Dropped frame')
    #         elif (i%(fac)) == 0:
    #             pulseAll(GPIOlist[1:3], 0.005) # Trigger for aquisition
    #             tsleep = ran[i+j] - (timer() - t0)
    #             if tsleep >= 0:
    #                 time.sleep(tsleep)
    #             else:
    #                 j+=1
    #                 print('Dropped frame')
    #         else:
    #             #send UDP to USB CPU
    #             pulseAll(GPIOlist[2:3],0.005)
    #             # if (i%100) == 0: 
    #             #     print('Triggering pi camera frame', i, 'of', nframe)
    #             #     print('Triggering CMOS camera frame', (i//fac), 'of', (nframe//fac))
    #             #print('time elapsed:', timer() - t0)
    #             #print('theoretical time:', n)
    #             tsleep = ran[i+j] - (timer() - t0)
    #             if tsleep >= 0:
    #                 time.sleep(tsleep)
    #             else:
    #                 j+=1
    #                 print('Dropped frame')

    #     else:
    #         if (i%(fac)) == 0:
    #             pulseAll(GPIOlist[1:3], 0.005) # Trigger for aquisition
    #             tsleep = ran[i+j] - (timer() - t0)
    #             if tsleep >= 0:
    #                 time.sleep(tsleep)
    #             else:
    #                 j+=1
    #                 print('Dropped frame')

    #         else:
    #             #send UDP to USB CPU
    #             pulseAll(GPIOlist[2:3],0.005)
    #             # if (i%100) == 0: 
    #             #     print('Triggering pi camera frame', i, 'of', nframe)
    #             #     print('Triggering CMOS camera frame', (i//fac), 'of', (nframe//fac))
    #             #print('time elapsed:', timer() - t0)
    #             #print('theoretical time:', n)
    #             tsleep = ran[i+j] - (timer() - t0)
    #             if tsleep >= 0:
    #                 time.sleep(tsleep)
    #             else:
    #                 j+=1
    #                 print('Dropped frame')
finally:
    print('brain camera time ' + str(timer()-t1) + ' sec(s)')
    print('total time pass ' + str(timer()-t0) + ' sec(s)')
    for pin in [camAquire, led1Blue, led2Blue, led3IR, led4IR]:
        pi.write(pin, 0)
    print("Shutting down.")
    pi.stop()
