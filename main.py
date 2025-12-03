from machine import Pin
import time
import onewire_lib

# Konfiguration
# GPIO 15: Data Pin
# WICHTIG: 4.7k Pull-Up Widerstand zwischen Data und 3.3V erforderlich!
PIN_NUM = 17

def main():
    print("=== Start 1-Wire Demo (MicroPython PIO) ===")
    
    try:
        ow = onewire_lib.OneWire(PIN_NUM)
    except Exception as e:
        print(f"Initialisierungsfehler: {e}")
        return

    # -----------------------------------------------------
    # 1. ROM Suche
    # -----------------------------------------------------
    print("Suche Geräte...")
    roms = ow.rom_search()
    
    if not roms:
        print("Keine Geräte gefunden.")
        print("Bitte Verkabelung und Pull-Up Widerstand prüfen.")
        return

    print(f"Gefunden: {len(roms)} Geräte")
    for i, rom in enumerate(roms):
        print(f"  [{i}] ID: 0x{rom:016x}")
    print("-" * 40)

    # -----------------------------------------------------
    # 2. Messschleife
    # -----------------------------------------------------
    while True:
        try:
            # A. Temperaturkonvertierung starten (Alle Sensoren gleichzeitig)
            if ow.reset():
                ow.write_byte(ow.SKIP_ROM)      # Broadcast
                ow.write_byte(ow.CONVERT_T)     # Start Messung (0x44)
                
                # Warten bis fertig (Polling)
                # Sensor zieht Datenleitung auf Low, solange er misst.
                timeout = 20 # max 1 Sekunde
                while timeout > 0:
                    time.sleep_ms(50)
                    if ow.read_byte() == 0xFF: # Fertig wenn High (0xFF)
                        break
                    timeout -= 1
                
                # B. Daten abholen
                print(f"Messung:")
                for i, rom in enumerate(roms):
                    if ow.reset():
                        ow.write_byte(ow.MATCH_ROM)
                        # ROM Code senden
                        for b in range(8):
                            ow.write_byte((rom >> (b * 8)) & 0xFF)
                        
                        ow.write_byte(ow.READ_SCRATCHPAD)
                        
                        # Alle 9 Bytes lesen (Daten + CRC)
                        scratchpad = bytearray(9)
                        for k in range(9):
                            scratchpad[k] = ow.read_byte()
                        
                        # CRC Prüfung (Daten + Checksumme muss 0 ergeben)
                        if ow.crc8(scratchpad) == 0:
                            # Temperatur berechnen (Byte 0 & 1)
                            raw = (scratchpad[1] << 8) | scratchpad[0]
                            if raw & 0x8000:
                                raw = -((raw ^ 0xFFFF) + 1)
                            temp_c = raw / 16.0
                            
                            # Auflösung auslesen (Byte 4)
                            res_cfg = (scratchpad[4] >> 5) & 0x03
                            res_bits = 9 + res_cfg
                            
                            print(f"  Dev {i}: {temp_c:6.2f} °C  (Res: {res_bits}-bit, CRC: OK)")
                        else:
                            print(f"  Dev {i}: CRC FEHLER! Daten verworfen.")
                            print(f"         Raw: {[hex(b) for b in scratchpad]}")
                    else:
                        print(f"  Dev {i}: Keine Antwort beim Lesen.")
                
            else:
                print("Bus-Reset fehlgeschlagen (Kein Sensor antwortet).")
                
        except Exception as e:
            print(f"Fehler in Schleife: {e}")
            # Versuch der Re-Initialisierung
            ow = onewire_lib.OneWire(PIN_NUM)

        print("-" * 40)
        time.sleep(2)

if __name__ == "__main__":
    main()