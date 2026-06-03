import struct

import numpy as np
import serial


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
SYNC = b'\xaa\x55'

# Packet layout (matches gnc_test main.cc):
#   [sync 2B][icm_accel 3f][icm_gyro 3f][icm_temp 1f][adxl_accel 3f][lis_mag 3f]['\n' 1B]
_N_FLOATS    = 13
_PKT_DATA_LEN = 4 * _N_FLOATS
PKT_TOTAL     = len(SYNC) + _PKT_DATA_LEN + 1


def open_serial():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"Opened {PORT} at {BAUD} baud\n")
    return ser


def read_packet(ser, rx):
    rx += ser.read(256)
    idx = rx.find(SYNC)
    if idx == -1:
        rx = rx[-1:]
        return None, rx
    if idx > 0:
        del rx[:idx]
    if len(rx) < PKT_TOTAL:
        return None, rx
    pkt = bytes(rx[len(SYNC):len(SYNC) + _PKT_DATA_LEN])
    del rx[:PKT_TOTAL]
    f = struct.unpack("<13f", pkt)
    return {
        "icm_accel":  np.array(f[0:3]),
        "icm_gyro":   np.array(f[3:6]),
        "icm_temp":   f[6],
        "adxl_accel": np.array(f[7:10]),
        "lis_mag":    np.array(f[10:13]),
    }, rx


def collect_static(ser, n, field):
    """Collect n packets at a fixed position. Returns (mean, std) arrays."""
    rx = bytearray()
    samples = []
    print(f"  Collecting {n} samples", end="", flush=True)
    while len(samples) < n:
        pkt, rx = read_packet(ser, rx)
        if pkt is None:
            continue
        samples.append(pkt[field])
        if len(samples) % (n // 10) == 0:
            print(".", end="", flush=True)
    print(" done")
    arr = np.array(samples)
    return np.mean(arr, axis=0), np.std(arr, axis=0)


def collect_moving(ser, n, field):
    """Collect n packets while sensor is moving. Returns raw sample array (n, 3)."""
    rx = bytearray()
    samples = []
    print(f"  Collecting {n} samples — move the sensor now", end="", flush=True)
    while len(samples) < n:
        pkt, rx = read_packet(ser, rx)
        if pkt is None:
            continue
        samples.append(pkt[field])
        if len(samples) % (n // 10) == 0:
            print(".", end="", flush=True)
    print(" done")
    return np.array(samples)
