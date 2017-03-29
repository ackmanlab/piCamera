import numpy as np
import cv2
import wholeBrain as wb
from hdf5manager import *
import time

start_time = time.time()
today = time.localtime()
timeString  = time.strftime("%Y%m%d", today)

#fnm = timeString[2:].upper()
exp = '_01'
fnm = '170328'
path = '/home/ackmanadmin/Documents/piCamera/data/' + fnm + '/' + fnm + exp
save_path = '/home/ackmanadmin/Documents/piCamera/data/' + fnm + exp
numframe = 12000
h = 450
w = 600

print("Saving to HDF5")
f = hdf5manager(save_path + '.hdf5')
f.save({'data_f': np.zeros((numframe, h, w), dtype=np.uint8)})
f.save({'data_b': np.zeros((numframe, h, w), dtype=np.uint8)})
f.open()

n = 0
while os.path.exists(path +'_c1-%05d.tif' % n):
    f.f['data_f'][n] = np.array(cv2.imread(path+ '_c1-%05d.tif' % n, 0), dtype = 'uint8')
    f.f['data_b'][n] = np.array(cv2.imread(path + '_c2-%05d.tif' % n, 0), dtype = 'uint8')
    n += 1
    if (n%100)==0:
        print('Saving frame:', n, ' of ', numframe)
f.close() 
