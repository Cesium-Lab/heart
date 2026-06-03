"""
ICM20948 calibration.
  Accel — 6-position static method: a_true = S * (a_raw - b)
  Gyro  — stationary bias:          w_true = w_raw - b
"""

import numpy as np
from common import open_serial, collect_static

G = 9.81
N_SAMPLES = 200

ACCEL_POSITIONS = [
    ("+X up", np.array([ G,  0,  0])),
    ("-X up", np.array([-G,  0,  0])),
    ("+Y up", np.array([ 0,  G,  0])),
    ("-Y up", np.array([ 0, -G,  0])),
    ("+Z up", np.array([ 0,  0,  G])),
    ("-Z up", np.array([ 0,  0, -G])),
]


def calibrate_accel(raw_means, references):
    b = np.zeros(3)
    s = np.zeros(3)
    for axis in range(3):
        A = np.column_stack([[ref[axis] for ref in references], np.ones(len(references))])
        y = np.array([raw[axis] for raw in raw_means])
        (inv_s, bias), *_ = np.linalg.lstsq(A, y, rcond=None)
        s[axis] = 1.0 / inv_s
        b[axis] = bias
    return b, s


def main():
    ser = open_serial()
    print("ICM20948 calibration")
    print("  Accel: a_true = S * (a_raw - b)")
    print("  Gyro:  w_true = w_raw - b\n")

    # ------------------------------------------------------------------
    # Accel
    # ------------------------------------------------------------------
    print("--- Accel (6 positions) ---\n")
    raw_means, references = [], []
    for label, ref in ACCEL_POSITIONS:
        input(f"Place sensor with {label}, then press Enter...")
        mean, std = collect_static(ser, N_SAMPLES, "icm_accel")
        print(f"  raw  x={mean[0]:8.4f}  y={mean[1]:8.4f}  z={mean[2]:8.4f}")
        print(f"  std  x={std[0]:8.4f}  y={std[1]:8.4f}  z={std[2]:8.4f}\n")
        raw_means.append(mean)
        references.append(ref)

    accel_b, accel_s = calibrate_accel(raw_means, references)

    # ------------------------------------------------------------------
    # Gyro
    # ------------------------------------------------------------------
    print("--- Gyro (stationary bias) ---\n")
    input("Place sensor flat and still, then press Enter...")
    gyro_b, gyro_std = collect_static(ser, N_SAMPLES, "icm_gyro")
    print(f"  raw  x={gyro_b[0]:8.4f}  y={gyro_b[1]:8.4f}  z={gyro_b[2]:8.4f}")
    print(f"  std  x={gyro_std[0]:8.4f}  y={gyro_std[1]:8.4f}  z={gyro_std[2]:8.4f}\n")

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    print("=== Result ===")
    print(f"accel_b = [{accel_b[0]:.6f}, {accel_b[1]:.6f}, {accel_b[2]:.6f}]")
    print(f"accel_S = [{accel_s[0]:.6f}, {accel_s[1]:.6f}, {accel_s[2]:.6f}]")
    print(f"gyro_b  = [{gyro_b[0]:.6f}, {gyro_b[1]:.6f}, {gyro_b[2]:.6f}]")

    print("\n=== Accel Verification ===")
    max_err = 0.0
    for (label, ref), raw in zip(ACCEL_POSITIONS, raw_means):
        cal = accel_s * (raw - accel_b)
        err = float(np.linalg.norm(cal - ref))
        max_err = max(max_err, err)
        print(f"  {label:8s}  cal=[{cal[0]:7.3f},{cal[1]:7.3f},{cal[2]:7.3f}]  |err|={err:.4f} m/s²")
    print(f"\n  max accel error: {max_err:.4f} m/s²")
    ser.close()


if __name__ == "__main__":
    main()
