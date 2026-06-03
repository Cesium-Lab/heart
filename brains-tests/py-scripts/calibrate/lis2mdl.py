"""
LIS2MDL magnetometer calibration — rotation method.
Rotate sensor through all orientations to map the full field sphere.
  Hard-iron bias:  b = (max + min) / 2  per axis
  Soft-iron scale: s = mean_radius / half_range  per axis
Model: B_true = s * (B_raw - b)
"""

import numpy as np
from common import open_serial, collect_moving

N_SAMPLES = 500   # rotate slowly for ~10-15 s at 40 Hz


def calibrate(samples):
    lo  = samples.min(axis=0)
    hi  = samples.max(axis=0)
    b   = (hi + lo) / 2.0
    half_ranges = (hi - lo) / 2.0
    for axis, hr in enumerate(half_ranges):
        if hr < 1.0:
            print(f"  [WARN] axis {'xyz'[axis]} range only {hr*2:.2f} µT — rotate more for a valid calibration")
    mean_radius = half_ranges.mean()
    s = mean_radius / half_ranges
    return b, s


def main():
    ser = open_serial()
    print("LIS2MDL calibration — model: B_true = s * (B_raw - b)")
    print("Rotate the sensor slowly through all orientations during collection.\n")

    input("Press Enter to start collecting...")
    samples = collect_moving(ser, N_SAMPLES, "lis_mag")

    lo = samples.min(axis=0)
    hi = samples.max(axis=0)
    print(f"\n  min  x={lo[0]:8.3f}  y={lo[1]:8.3f}  z={lo[2]:8.3f} µT")
    print(f"  max  x={hi[0]:8.3f}  y={hi[1]:8.3f}  z={hi[2]:8.3f} µT")

    b, s = calibrate(samples)

    print("\n=== Result ===")
    print(f"b = [{b[0]:.6f}, {b[1]:.6f}, {b[2]:.6f}]  µT")
    print(f"s = [{s[0]:.6f}, {s[1]:.6f}, {s[2]:.6f}]")

    cal = s * (samples - b)
    norms = np.linalg.norm(cal, axis=1)
    print(f"\n=== Verification ===")
    print(f"  |B| mean: {norms.mean():.3f} µT  std: {norms.std():.3f} µT")
    print(f"  (ideally std ≈ 0, mean ≈ local field magnitude ~25–65 µT)")
    ser.close()


if __name__ == "__main__":
    main()
