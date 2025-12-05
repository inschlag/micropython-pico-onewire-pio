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