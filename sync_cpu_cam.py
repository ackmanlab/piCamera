import pigpio
from timeit import default_timer as timer
import socket
import numpy as np
import time
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("-l", "--length", type = float, default = 1,
                help="desired video length in minutes")
ap.add_argument("-t", "--ttl", type = int, default = 10,
                help="ttl frequency")
ap.add_argument("-u", "--USB", type=int, default=30,
                help="UDP frequency for USB cameras")
ap.add_argument("-d", "--dict", type = argparse.FileType('r'),
                nargs = 1, required = False,
                help="name/host/port dict for communication")
args = vars(ap.parse_args())

#intial parameters for camera rates
fpscMOS = args['ttl'] #fps for cMOS camera
fpsUSB = args['USB'] #fps for USB camera
mlen = args['length'] # in minutes
timesec = mlen * 60
lag = 0 #0.0002

#define how the communication will occur through ethernet
name = ['sUSB', 'sCMOS'] 
hosts = ['128.114.78.96', '128.114.78.191']
ports = [ 8936, 8940 ]

#calculating looping parameters
if fpscMOS >= fpsUSB:
    nframe = timesec * fpscMOS #(min * 60sec/min * fps)
    step = 1 / fpscMOS + lag
    fac = fpscMOS / fpsUSB
if fpscMOS << fpsUSB:
    nframe = timesec * fpsUSB
    step = 1 / fpsUSB + lag
    fac = fpsUSB / fpscMOS

ran = np.arange(0, (mlen * 60) + step, step)
#ran = np.arange(0, 10 + step, step)

#server and communication setup
def setupServer(name, host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print ("Socket created.")
    try:
        s.bind((host, port))
        print ('Socket', name, 'bound to ', host, ' : ', port)
    except socket.error as msg:
        print(msg)
    return s
    
#TTL write
def pulse(GPIO, dur):
    pi.write(GPIO, 1) # high
    time.sleep(dur) # in sec
    pi.write(GPIO, 0) # low

#initialize handles for TTL and UDP
#sCMOS = setupServer(name[1], hosts[1], ports[1]) #UDP to CMOS CPU
sUSB = setupServer(name[0], hosts[0], ports[0]) #UDP to USB CPU
pi = pigpio.pi() #TTL

#for loop sending information
t0 = timer()
pi.write(12, 1) #light blue two
pi.write(23, 1) #light blue one
for i, n in enumerate(ran[:-1]):
    #send TTL
    if (i%(fac)) == 0:
        pulse(24, 0.01)
        #send UDP to USB CPU
        #sCMOS.sendto(str.encode(str(i//fac)), (hosts[1], ports[1]))
    #send UDP to USB CPU
    sUSB.sendto(str.encode(str(i//1)), (hosts[0], ports[0]))
    if (i%100) == 0: 
        print('Triggering USB camera frame', i, 'of', nframe)
        print('Triggering CMOS camera frame', (i//fac), 'of', (nframe//fac))
    #print('time elapsed:', timer() - t0)
    #print('theoretical time:', n)
    tsleep = ran[i+1] - (timer() - t0) 
    time.sleep(tsleep)

pi.write(12, 0)
pi.write(23, 0)

print("Shutting down.")
pi.stop()
#sCMOS.close()
sUSB.close()
