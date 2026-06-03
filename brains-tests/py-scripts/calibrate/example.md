
```
((venv) ) Europa-Clipper-4:calibrate magi-nerv$ python ./icm20948.py
Opened /dev/tty.usbserial-0001 at 115200 baud

ICM20948 calibration
  Accel: a_true = S * (a_raw - b)
  Gyro:  w_true = w_raw - b

--- Accel (6 positions) ---

Place sensor with +X up, then press Enter...
  Collecting 200 samples.......... done
  raw  x= -0.0852  y= -0.3035  z=  9.8877
  std  x=  0.5576  y=  1.2104  z=  0.8368

Place sensor with -X up, then press Enter...
  Collecting 200 samples.......... done
  raw  x=  1.8931  y= -1.2065  z=  0.3065
  std  x=  9.1790  y=  2.5211  z=  0.9589

Place sensor with +Y up, then press Enter...
  Collecting 200 samples.......... done
  raw  x= -8.1267  y= -1.2175  z=  3.9814
  std  x=  1.8737  y=  1.2365  z=  3.2050

Place sensor with -Y up, then press Enter...
  Collecting 200 samples.......... done
  raw  x= -0.1871  y= -9.9535  z=  0.2953
  std  x=  0.0291  y=  0.0293  z=  0.0309

Place sensor with +Z up, then press Enter...
  Collecting 200 samples.......... done
  raw  x= -0.2372  y=  9.4488  z=  0.7103
  std  x=  0.4931  y=  0.9380  z=  1.9256

Place sensor with -Z up, then press Enter...
  Collecting 200 samples.......... done
  raw  x= -0.0693  y=  0.3111  z=  9.8959
  std  x=  0.0283  y=  0.0310  z=  0.0348

--- Gyro (stationary bias) ---

Place sensor flat and still, then press Enter...
  Collecting 200 samples.......... done
  raw  x=  0.3210  y=  0.5957  z= -0.5622
  std  x=  0.3537  y=  0.2743  z=  0.1420

=== Result ===
accel_b = [-1.135386, -0.486857, 4.179520]
accel_S = [-9.917582, 2.245864, -2.135945]
gyro_b  = [0.321037, 0.595732, -0.562195]

=== Accel Verification ===
  +X up     cal=[-10.416,  0.412,-12.192]  |err|=23.6200 m/s²
  -X up     cal=[-30.036, -1.616,  8.272]  |err|=21.9117 m/s²
  +Y up     cal=[ 69.337, -1.641,  0.423]  |err|=70.2772 m/s²
  -Y up     cal=[ -9.405,-21.261,  8.297]  |err|=16.9824 m/s²
  +Z up     cal=[ -8.908, 22.314,  7.410]  |err|=24.1460 m/s²
  -Z up     cal=[-10.573,  1.792,-12.210]  |err|=10.9893 m/s²

  max accel error: 70.2772 m/s²
```