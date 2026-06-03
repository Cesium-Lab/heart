"""
ADXL375 accelerometer calibration — 6-position static method.
Model: a_true = S * (a_raw - b)
"""

import numpy as np
from common import open_serial, collect_static

G = 9.81
N_SAMPLES = 200

POSITIONS = [
    ("+X up", np.array([ G,  0,  0])),
    ("-X up", np.array([-G,  0,  0])),
    ("+Y up", np.array([ 0,  G,  0])),
    ("-Y up", np.array([ 0, -G,  0])),
    ("+Z up", np.array([ 0,  0,  G])),
    ("-Z up", np.array([ 0,  0, -G])),
]


def calibrate(raw_means, references):
    """Solve per-axis: a_raw = (1/S)*a_true + b via least squares."""
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
    print("ADXL375 calibration — model: a_true = S * (a_raw - b)\n")

    raw_means, references = [], []
    for label, ref in POSITIONS:
        input(f"Place sensor with {label}, then press Enter...")
        mean, std = collect_static(ser, N_SAMPLES, "adxl_accel")
        print(f"  raw  x={mean[0]:8.4f}  y={mean[1]:8.4f}  z={mean[2]:8.4f}")
        print(f"  std  x={std[0]:8.4f}  y={std[1]:8.4f}  z={std[2]:8.4f}\n")
        raw_means.append(mean)
        references.append(ref)

    b, s = calibrate(raw_means, references)

    print("=== Result ===")
    print(f"b = [{b[0]:.6f}, {b[1]:.6f}, {b[2]:.6f}]")
    print(f"S = [{s[0]:.6f}, {s[1]:.6f}, {s[2]:.6f}]")

    print("\n=== Verification ===")
    max_err = 0.0
    for (label, ref), raw in zip(POSITIONS, raw_means):
        cal = s * (raw - b)
        err = float(np.linalg.norm(cal - ref))
        max_err = max(max_err, err)
        print(f"  {label:8s}  cal=[{cal[0]:7.3f},{cal[1]:7.3f},{cal[2]:7.3f}]  |err|={err:.4f} m/s²")
    print(f"\n  max error: {max_err:.4f} m/s²")
    ser.close()


if __name__ == "__main__":
    main()
