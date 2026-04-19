import struct
import time
from collections import deque

import serial
import numpy as np
import matplotlib.pyplot as plt


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
N_FLOATS = 3
PKT_LEN = 4 * N_FLOATS            # 12 bytes for 4 floats

# ring buffers for plotting
BUF_N = 20
t = deque(maxlen=BUF_N)
ys = [deque(maxlen=BUF_N) for _ in range(N_FLOATS)]

ser = serial.Serial(PORT, BAUD, timeout=0.1)

plt.ion()
fig, ax = plt.subplots()
lines = [ax.plot([], [])[0] for _ in range(N_FLOATS)]
ax.set_xlabel("sample")
ax.set_ylabel("value")
ax.grid(True)

rx = bytearray()
k = 0

while True:
    rx += ser.read(4096)

    # parse fixed-length packets
    while len(rx) >= PKT_LEN:
        pkt = bytes(rx[:PKT_LEN])
        del rx[:PKT_LEN]

        vals = struct.unpack("<3f", pkt)   # little-endian 3 floats
        t.append(k); k += 1
        for i, v in enumerate(vals):
            ys[i].append(v)

        print(vals)   # print the values to console

    # update plot
    if len(t) > 2:
        x = np.fromiter(t, dtype=np.int32)
        for i in range(N_FLOATS):
            y = np.fromiter(ys[i], dtype=np.float32)
            lines[i].set_data(x, y)

        ax.relim()
        ax.set_ylim(-20, 20)
        ax.autoscale_view()
        plt.pause(0.01)

