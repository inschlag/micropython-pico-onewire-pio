import time

class DS18B20:
    def __init__(self, onewire):
        """
        Initialisiert den DS18B20 Manager.
        :param onewire: Eine Instanz der OneWire Klasse (aus onewire_lib)
        """
        self.ow = onewire
        self.roms = []

    def scan(self):
        """
        Sucht nach Geräten am Bus und speichert die Liste intern.
        :return: Liste der gefundenen ROM-Codes
        """
        self.roms = self.ow.rom_search()
        return self.roms

    def read_temperatures(self):
        """
        Führt den kompletten Zyklus durch:
        1. Startet Konvertierung auf ALLEN Sensoren (Broadcast).
        2. Wartet aktiv, bis die Messung fertig ist.
        3. Liest alle Sensoren nacheinander aus (mit CRC-Check).
        
        :return: Eine Liste von Tupeln: [(ROM_HEX_STRING, TEMPERATUR), ...]
        """
        results = []
        
        # Falls keine Geräte bekannt sind, abbrechen
        if not self.roms:
            return []

        # --- Schritt 1: Konvertierung starten ---
        if self.ow.reset():
            self.ow.write_byte(self.ow.SKIP_ROM)      # Broadcast an alle
            self.ow.write_byte(self.ow.CONVERT_T)     # Start Messung
            
            # --- Schritt 2: Warten auf Fertigstellung ---
            # Der Sensor zieht die Datenleitung auf Low, solange er misst.
            # Sobald er fertig ist, geht sie auf High (durch Pull-Up).
            # Max Zeit für 12-bit ist 750ms. Wir pollen alle 10ms.
            timeout = 100 # 100 * 10ms = 1 Sekunde Timeout
            while timeout > 0:
                time.sleep_ms(10)
                if self.ow.read_byte() == 0xFF: # Liest 1en -> Fertig
                    break
                timeout -= 1
        else:
            # Bus Reset fehlgeschlagen (keine Sensoren verbunden?)
            return []

        # --- Schritt 3: Auslesen der Ergebnisse ---
        for rom in self.roms:
            if self.ow.reset():
                self.ow.write_byte(self.ow.MATCH_ROM)
                
                # 64-Bit ROM senden
                for b in range(8):
                    self.ow.write_byte((rom >> (b * 8)) & 0xFF)
                
                self.ow.write_byte(self.ow.READ_SCRATCHPAD)
                
                # 9 Bytes lesen (Daten + CRC)
                data = bytearray(9)
                for i in range(9):
                    data[i] = self.ow.read_byte()
                
                # CRC Prüfung mit der Methode aus der OneWire Klasse
                if self.ow.crc8(data) == 0:
                    # Temperatur berechnen
                    raw = (data[1] << 8) | data[0]
                    if raw & 0x8000:
                        raw = -((raw ^ 0xFFFF) + 1)
                    temp_c = raw / 16.0
                    
                    # Ergebnis formatieren
                    rom_str = f"0x{rom:016x}"
                    results.append((rom_str, temp_c))
                else:
                    # Bei CRC Fehler geben wir None als Temperatur zurück
                    rom_str = f"0x{rom:016x}"
                    results.append((rom_str, None))
                    
        return results