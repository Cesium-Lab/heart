import struct
import sys

import numpy as np
import serial


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
N_FLOATS = 3
SYNC = b'\xaa\x55'
ADXL_EXPECTED_ID = 0xE5
PKT_DATA_LEN = 4 * N_FLOATS
PKT_TOTAL = len(SYNC) + 1 + PKT_DATA_LEN + 1  # sync + chip_id + data + '\n'

G = 9.81  # m/s^2
N_SAMPLES = 200  # samples averaged per position

POSITIONS = [
    ("+X up", np.array([ G,  0,  0])),
    ("-X up", np.array([-G,  0,  0])),
    ("+Y up", np.array([ 0,  G,  0])),
    ("-Y up", np.array([ 0, -G,  0])),
    ("+Z up", np.array([ 0,  0,  G])),
    ("-Z up", np.array([ 0,  0, -G])),
]


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
    chip_id = rx[len(SYNC)]
    data_start = len(SYNC) + 1
    pkt = bytes(rx[data_start:data_start + PKT_DATA_LEN])
    del rx[:PKT_TOTAL]
    vals = np.array(struct.unpack("<3f", pkt))
    return (chip_id, vals), rx


def collect_samples(ser, n):
    rx = bytearray()
    samples = []
    print(f"  Collecting {n} samples", end="", flush=True)
    while len(samples) < n:
        result, rx = read_packet(ser, rx)
        if result is None:
            continue
        chip_id, vals = result
        if chip_id != ADXL_EXPECTED_ID:
            print(f"\n  [FAIL] Bad chip ID: 0x{chip_id:02X}, expected 0x{ADXL_EXPECTED_ID:02X}")
            sys.exit(1)
        samples.append(vals)
        if len(samples) % (n // 10) == 0:
            print(".", end="", flush=True)
    print(" done")
    return np.mean(samples, axis=0), np.std(samples, axis=0)


def calibrate(raw_means, references):
    """
    Solve per-axis: a_raw = (1/S) * a_true + b  (linear in 1/S and b)
    Returns b (bias, shape 3) and S (scale, shape 3).
    """
    b = np.zeros(3)
    s = np.zeros(3)
    for axis in range(3):
        A = np.column_stack([
            [ref[axis] for ref in references],
            np.ones(len(references)),
        ])
        y = np.array([raw[axis] for raw in raw_means])
        (inv_s, bias), *_ = np.linalg.lstsq(A, y, rcond=None)
        s[axis] = 1.0 / inv_s
        b[axis] = bias
    return b, s


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"Opened {PORT} at {BAUD} baud")
    print(f"Model: a_true = S * (a_raw - b)\n")

    raw_means = []
    references = []

    for label, ref in POSITIONS:
        input(f"Place sensor with {label}, then press Enter...")
        mean, std = collect_samples(ser, N_SAMPLES)
        print(f"  raw  x={mean[0]:8.4f}  y={mean[1]:8.4f}  z={mean[2]:8.4f}")
        print(f"  std  x={std[0]:8.4f}  y={std[1]:8.4f}  z={std[2]:8.4f}")
        raw_means.append(mean)
        references.append(ref)
        print()

    b, s = calibrate(raw_means, references)

    print("=== Calibration Result ===")
    print(f"b = [{b[0]:.6f}, {b[1]:.6f}, {b[2]:.6f}]")
    print(f"S = [{s[0]:.6f}, {s[1]:.6f}, {s[2]:.6f}]")
    print()

    print("=== Verification ===")
    max_err = 0.0
    for (label, ref), raw in zip(POSITIONS, raw_means):
        cal = s * (raw - b)
        err = float(np.linalg.norm(cal - ref))
        max_err = max(max_err, err)
        print(f"  {label:8s}  cal=[{cal[0]:7.3f}, {cal[1]:7.3f}, {cal[2]:7.3f}]  |err|={err:.4f} m/s²")
    print(f"\n  max error: {max_err:.4f} m/s²")

    ser.close()


if __name__ == "__main__":
    main()
