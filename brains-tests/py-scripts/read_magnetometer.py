import struct
import time
from collections import deque

import serial
import numpy as np
import matplotlib.pyplot as plt


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
N_FLOATS = 3
SYNC = b'\xaa\x55'
PKT_LEN = 4 * N_FLOATS            # 12 bytes for 4 floats
ADXL_EXPECTED_ID = 0xE5
PKT_DATA_LEN = 4 * N_FLOATS       # 12 bytes of float payload
PKT_TOTAL = len(SYNC) + 1 + PKT_DATA_LEN + 1  # sync + chip_id + data + '\n'

# ring buffers for plotting
BUF_N = 100
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

    while True:
        idx = rx.find(SYNC)
        if idx == -1:
            rx = rx[-1:]   # keep last byte in case it's the first sync byte
            break
        if idx > 0:
            del rx[:idx]   # discard junk before sync header
        if len(rx) < PKT_TOTAL:
            break          # wait for more bytes

        chip_id = rx[len(SYNC)]
        data_start = len(SYNC) + 1
        pkt = bytes(rx[data_start:data_start + PKT_DATA_LEN])
        del rx[:PKT_TOTAL]

        vals = struct.unpack("<3f", pkt)   # little-endian 3 floats
        t.append(k); k += 1
        for i, v in enumerate(vals):
            ys[i].append(v)

        id_ok = chip_id == ADXL_EXPECTED_ID
        print(f"[{'OK' if id_ok else 'FAIL'} chip_id=0x{chip_id:02X}] {vals}")

    # update plot
    if len(t) > 2:
        x = np.fromiter(t, dtype=np.int32)
        for i in range(N_FLOATS):
            y = np.fromiter(ys[i], dtype=np.float32)
            lines[i].set_data(x, y)

        ax.relim()
        ax.set_ylim(-20, 20)
        ax.autoscale_view()
        fig.canvas.draw_idle()
        fig.canvas.flush_events()