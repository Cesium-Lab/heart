# Overview

Has been managed by Special Interest Group (SIG), and used to be standardized by [IEEE 802.15.1](https://en.wikipedia.org/wiki/IEEE_802.15) (IEEE working group numbers are really cool, like 802.3 for Ethernet and 802.11 for WLAN/WiFi)


# History of Bluetooth
### The name:
- Comes from a Danish king named Harald Bluetooth, 
- Was only intended as a placeholder
- Going to be PAN (Personal Area Networks)
  - It was already was used a lot on the internet for general PANs
- Then RadioWire was considered 
  - Couldn't complete a full trademark search, so went with Bluetooth

### Development of Special Interest Group (SIG)
- "short-link" radio technology in Lund, Sweden (at Ericsson Mobile)
- Started in 1989, had solution by 1997
- IBM R&D collaboration
  - Tried to put into ThinkPad (with mobile phone), but power req. too high
- Made short-link radio tech OPEN INDUSTRY STANDARD
  - Recruited Intel, who also recruited Toshiba and Nokia
- 1998 - Made Bluetooth Special Interest Group (SIG)


### Early dev
- Products!
  - 1999 - Hands-free mobile headset (wikipedia not clear what it actually was)
    - "Best of show Technology Award" at [COMDEX](https://en.wikipedia.org/wiki/COMDEX) (COMputer Dealers' EXhibition in Vegas, super cool thing).
  - 2001 Q1 - Erisson model T39 (First mobile phone)
  - 2001/06 - Erisson model T39 (First mobile phone)
  - 2001/10 - IBM ThinkPad A30 (First notebook)
- Vosi tried to implement into phone-vehicle link (WiFi not that available or widely used yet) but lost legal battle against Motorola

# Current standards

### Transmission
- 2.4 Ghz (2.402 and 2.480)
  - In unlicensed industrial, scientific and medical (ISM) 
- [Frequency-hopping spread spectrum](https://en.wikipedia.org/wiki/Frequency-hopping_spread_spectrum)
- 79 channels - 1 MHz bandwidth
- 1600 hops/second
- Datarate
  - 1 Mbits/s for Gaussian frequency-shift keying (GFSK)
  - Up to 8 with other

### Network
- Packet-based
- Master/slave
  - Can communicate with up to 7 slaves
  - [Piconet](https://en.wikipedia.org/wiki/Piconet) - kinda cool
    - Can have 7 active slaves, with 255 "parked" but inactive
    - Anyone can become master
    - Multiple form a [scatternet](https://en.wikipedia.org/wiki/Scatternet)
    - Usually round-robin fashion
- Use master clock (312.5  &#x03BC;s)
- TX/RX every other slot

### Classes/Power
- Lower = more power
- Most Bluetooth is batery-powered Class 2
- Range
  - Order of magnitude of 10-100m
  - [Bluetooth Official Site](https://www.bluetooth.com/learn-about-bluetooth/key-attributes/range/) says like ~25-50m
![alt text](utils/image.png)

### Profiles
- Each device needs to interpret certain profiles
  - Headset Profile (HSP) - connects headphones and earbuds to a cell phone or laptop.
  - Health Device Profile (HDP) - can connect a cell phone to a digital thermometer or heart rate detector.
  - Video Distribution Profile (VDP) - sends a video stream from a video camera to a TV screen or a recording device.

## BLE

- 40 channels - 2 MHz bandwidth
- Transmit power 10 mW (from 2.5 mW)
- Smaller range (lower energy, duh)
- Wakes in 6 ms (from 100 ms)
- 10-500 mW (from 1000 mW as reference)

Links
- [wiki](https://en.wikipedia.org/wiki/Bluetooth)
- [Architecture](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/architecture,-mixing,-and-conventions/architecture.html)

# Overview
- 2.4 GHz ISM (industrial, scientific, and medical)
- For Personal Area Networks (PAN)
- Frequency Hopping
- Uses (besides the classic stuff)
  - File transfers, phone tethering, ~10-30m range high-bandwidth links
- Links
  - [ezurio article](https://www.ezurio.com/resources/blog/bluetooth-low-energy-vs-bluetooth-classic-what-s-the-difference)

## Cool devices

- [micro:bit](https://microbit.org/)
  - Cool board for learnign 
  - ARM-based (yay)
- [ESP-32 WOW](https://dronebotworkshop.com/esp32-bluetooth/)
  - I guess we can do Bluetooth with ESPs (I thought they only had WiFi)
  - 