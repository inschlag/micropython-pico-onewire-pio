# MicroPython 1-Wire PIO Driver for Raspberry Pi Pico (RP2040 & RP2350)

A robust, high-precision 1-Wire driver for MicroPython on the Raspberry Pi Pico, implemented using the **PIO (Programmable I/O)** state machines.

This library is a port of the pio onewire from [onewire](https://github.com/raspberrypi/pico-examples/tree/master/pio/onewire)  adapted and optimized for MicroPython. It solves common timing issues associated with bit-banging 1-Wire in Python by offloading the critical timing to the PIO hardware.

## Features

* **Precision Timing:** Utilizes PIO assembly to guarantee microsecond-accurate time slots (1µs resolution), independent of CPU load or Python Garbage Collection.
* **RP2350 Compatible:** Works seamlessly on both Raspberry Pi Pico (RP2040) and Pico 2 (RP2350).
* **Robust Reset:** Reset Pulse (>480µs).
* **FIFO Synchronization:** Implements strict lock-step synchronization between Python and PIO to prevent FIFO overflows during `write` operations.
* **CRC-8 Support:** Built-in helper for CRC checks to ensure data integrity over longer cable runs.
* **Safe Initialization:** Configures pins as `INPUT PULLUP` on startup to prevent blocking the bus.

## Hardware Requirements

* **Raspberry Pi Pico** (or Pico W / Pico 2)
* **1-Wire Device** (e.g., DS18B20 Temperature Sensor)
* **4.7kΩ Resistor** (Required as a Pull-Up between Data and 3.3V)

### Wiring

| Pico Pin | Device Pin | Notes |
| :--- | :--- | :--- |
| **3.3V (Out)** | VCC (VDD) | Do not use 5V |
| **GND** | GND | Common Ground |
| **GPIO X** | DATA (DQ) | Any GPIO pin (e.g., GP15) |

**Important:** You **must** connect a 4.7kΩ resistor between the **DATA** pin and **3.3V**. 1-Wire is an open-drain protocol; without this resistor, communication will fail.

## Installation

1.  Download `onewire_lib.py`.
2.  Upload it to the root directory of your Raspberry Pi Pico using Thonny or mpremote.
3.  Upload `main.py` (example usage) or use the snippets below.

## Usage

### Basic Example: Reading DS18B20 Temperature

```python
import time
from onewire_pio_lib import OneWire
from ds18b20 import DS18B20

# Konfiguration
PIN_NUM = 17  # GPIO 15 (mit 4.7k Pull-Up!)

def main():
    print("Start DS18B20 System...")
    
    # 1. Objekte anlegen
    ow = OneWire(PIN_NUM)
    sensor_mgr = DS18B20(ow)
    
    # 2. Einmalig scannen
    print("Scanne Bus...")
    found = sensor_mgr.scan()
    print(f"{len(found)} Sensoren gefunden.")
    
    # 3. Periodisch abfragen
    while True:
        try:
            print("Messe...")
            # Diese Methode kümmert sich um alles (Convert, Wait, CRC)
            readings = sensor_mgr.read_temperatures()
            
            for rom_id, temp in readings:
                if temp is not None:
                    print(f"  ID: {rom_id} -> {temp:.2f} °C")
                else:
                    print(f"  ID: {rom_id} -> CRC Fehler!")
            
            print("-" * 30)
            
        except Exception as e:
            print(f"Fehler: {e}")
            # Bei groben Fehlern (z.B. Kabelbruch) ggf. neu scannen
            # sensor_mgr.scan() 
        
        time.sleep(2)

if __name__ == "__main__":
    main()