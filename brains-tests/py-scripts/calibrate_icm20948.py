import struct
import sys

import numpy as np
import serial


PORT = "/dev/tty.usbserial-0001"   # change
BAUD = 115200
SYNC = b'\xaa\x55'
ICM_EXPECTED_ID = 0xEA

# Packet: [0xAA][0x55][chip_id][accel x,y,z (3f)][gyro x,y,z (3f)]['\n']
PKT_DATA_LEN = 4 * 6   # 6 floats = 24 bytes
PKT_TOTAL = len(SYNC) + 1 + PKT_DATA_LEN + 1  # 28 bytes

G = 9.81        # m/s^2
N_SAMPLES = 200

ACCEL_POSITIONS = [
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
    floats = struct.unpack("<6f", bytes(rx[data_start:data_start + PKT_DATA_LEN]))
    del rx[:PKT_TOTAL]
    accel = np.array(floats[0:3])
    gyro  = np.array(floats[3:6])
    return (chip_id, accel, gyro), rx


def collect_samples(ser, n):
    rx = bytearray()
    accel_samples = []
    gyro_samples  = []
    print(f"  Collecting {n} samples", end="", flush=True)
    while len(accel_samples) < n:
        result, rx = read_packet(ser, rx)
        if result is None:
            continue
        chip_id, accel, gyro = result
        if chip_id != ICM_EXPECTED_ID:
            print(f"\n  [FAIL] Bad chip ID: 0x{chip_id:02X}, expected 0x{ICM_EXPECTED_ID:02X}")
            sys.exit(1)
        accel_samples.append(accel)
        gyro_samples.append(gyro)
        if len(accel_samples) % (n // 10) == 0:
            print(".", end="", flush=True)
    print(" done")
    return (
        np.mean(accel_samples, axis=0), np.std(accel_samples, axis=0),
        np.mean(gyro_samples,  axis=0), np.std(gyro_samples,  axis=0),
    )


def calibrate_accel(raw_means, references):
    """
    Solve per-axis: a_raw = (1/S) * a_true + b
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
    print(f"ICM20948 calibration")
    print(f"  Accel model: a_true = S * (a_raw - b)")
    print(f"  Gyro  model: w_true = w_raw - b\n")

    # ------------------------------------------------------------------
    # Accel calibration — 6 positions
    # ------------------------------------------------------------------
    print("--- Accel calibration (6 positions) ---\n")
    accel_means = []
    references  = []

    for label, ref in ACCEL_POSITIONS:
        input(f"Place sensor with {label}, then press Enter...")
        a_mean, a_std, _, _ = collect_samples(ser, N_SAMPLES)
        print(f"  accel raw  x={a_mean[0]:8.4f}  y={a_mean[1]:8.4f}  z={a_mean[2]:8.4f}")
        print(f"  accel std  x={a_std[0]:8.4f}  y={a_std[1]:8.4f}  z={a_std[2]:8.4f}")
        accel_means.append(a_mean)
        references.append(ref)
        print()

    accel_b, accel_s = calibrate_accel(accel_means, references)

    # ------------------------------------------------------------------
    # Gyro calibration — stationary bias
    # ------------------------------------------------------------------
    print("--- Gyro calibration (stationary) ---\n")
    input("Place sensor flat and still, then press Enter...")
    _, _, g_mean, g_std = collect_samples(ser, N_SAMPLES)
    print(f"  gyro raw  x={g_mean[0]:8.4f}  y={g_mean[1]:8.4f}  z={g_mean[2]:8.4f}")
    print(f"  gyro std  x={g_std[0]:8.4f}  y={g_std[1]:8.4f}  z={g_std[2]:8.4f}\n")
    gyro_b = g_mean  # true rate is 0 when stationary

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    print("=== Calibration Result ===")
    print(f"accel_b = [{accel_b[0]:.6f}, {accel_b[1]:.6f}, {accel_b[2]:.6f}]")
    print(f"accel_S = [{accel_s[0]:.6f}, {accel_s[1]:.6f}, {accel_s[2]:.6f}]")
    print(f"gyro_b  = [{gyro_b[0]:.6f}, {gyro_b[1]:.6f}, {gyro_b[2]:.6f}]")
    print()

    print("=== Accel Verification ===")
    max_err = 0.0
    for (label, ref), raw in zip(ACCEL_POSITIONS, accel_means):
        cal = accel_s * (raw - accel_b)
        err = float(np.linalg.norm(cal - ref))
        max_err = max(max_err, err)
        print(f"  {label:8s}  cal=[{cal[0]:7.3f}, {cal[1]:7.3f}, {cal[2]:7.3f}]  |err|={err:.4f} m/s²")
    print(f"\n  max accel error: {max_err:.4f} m/s²")

    ser.close()


if __name__ == "__main__":
    main()
