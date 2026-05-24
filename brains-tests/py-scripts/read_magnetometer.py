import struct
from collections import deque

import serial
import numpy as np
import matplotlib.pyplot as plt


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
SYNC = b'\xaa\x55'

# Packet layout (no chip_id):
#   [sync 2B][icm_accel 3f][icm_gyro 3f][icm_temp 1f][adxl_accel 3f][lis_mag 3f]['\n' 1B]
N_FLOATS   = 13
PKT_DATA_LEN = 4 * N_FLOATS        # 52 bytes
PKT_TOTAL    = len(SYNC) + PKT_DATA_LEN + 1  # 55 bytes

BUF_N = 100

# Ring buffers: icm_accel, icm_gyro, icm_temp, adxl_accel, lis_mag
bufs = {
    "icm_accel": [deque(maxlen=BUF_N) for _ in range(3)],
    "icm_gyro":  [deque(maxlen=BUF_N) for _ in range(3)],
    "icm_temp":  [deque(maxlen=BUF_N)],
    "adxl_accel":[deque(maxlen=BUF_N) for _ in range(3)],
    "lis_mag":   [deque(maxlen=BUF_N) for _ in range(3)],
}
t = deque(maxlen=BUF_N)

ser = serial.Serial(PORT, BAUD, timeout=0.1)

fig, axes = plt.subplots(5, 1, figsize=(10, 12), sharex=True)
fig.suptitle("Sensor Readout")
plt.ion()

PLOT_CFG = [
    ("icm_accel", axes[0], "ICM Accel [m/s²]",  ["x", "y", "z"],    (-20, 20)),
    ("icm_gyro",  axes[1], "ICM Gyro [dps]",     ["x", "y", "z"],    (-200, 200)),
    ("icm_temp",  axes[2], "ICM Temp [°C]",      ["T"],              (15, 45)),
    ("adxl_accel",axes[3], "ADXL Accel [m/s²]",  ["x", "y", "z"],    (-400, 400)),
    ("lis_mag",   axes[4], "LIS Mag [µT]",        ["x", "y", "z"],    (-100, 100)),
]

lines = {}
for key, ax, ylabel, labels, ylim in PLOT_CFG:
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.grid(True)
    lines[key] = [ax.plot([], [], label=lbl)[0] for lbl in labels]
    ax.legend(loc="upper left", fontsize=7)

axes[-1].set_xlabel("sample")
plt.tight_layout()

rx = bytearray()
k = 0

while True:
    rx += ser.read(4096)

    while True:
        idx = rx.find(SYNC)
        if idx == -1:
            rx = rx[-1:]
            break
        if idx > 0:
            del rx[:idx]
        if len(rx) < PKT_TOTAL:
            break

        pkt = bytes(rx[len(SYNC):len(SYNC) + PKT_DATA_LEN])
        del rx[:PKT_TOTAL]

        f = struct.unpack("<13f", pkt)
        icm_accel = f[0:3]
        icm_gyro  = f[3:6]
        icm_temp  = f[6]
        adxl_accel= f[7:10]
        lis_mag   = f[10:13]

        t.append(k); k += 1
        for i in range(3): bufs["icm_accel"][i].append(icm_accel[i])
        for i in range(3): bufs["icm_gyro"][i].append(icm_gyro[i])
        bufs["icm_temp"][0].append(icm_temp)
        for i in range(3): bufs["adxl_accel"][i].append(adxl_accel[i])
        for i in range(3): bufs["lis_mag"][i].append(lis_mag[i])

        print(
            f"icm_a=({icm_accel[0]:7.3f},{icm_accel[1]:7.3f},{icm_accel[2]:7.3f}) "
            f"icm_g=({icm_gyro[0]:7.3f},{icm_gyro[1]:7.3f},{icm_gyro[2]:7.3f}) "
            f"t={icm_temp:.1f}°C  "
            f"adxl=({adxl_accel[0]:7.3f},{adxl_accel[1]:7.3f},{adxl_accel[2]:7.3f}) "
            f"mag=({lis_mag[0]:7.3f},{lis_mag[1]:7.3f},{lis_mag[2]:7.3f})"
        )

    if len(t) > 2:
        x = np.fromiter(t, dtype=np.int32)
        for key, ax, _, _, _ in PLOT_CFG:
            for i, line in enumerate(lines[key]):
                y = np.fromiter(bufs[key][i], dtype=np.float32)
                line.set_data(x, y)
            ax.relim()
            ax.autoscale_view(scaley=False)

        plt.pause(0.001)
