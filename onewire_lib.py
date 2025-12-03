import rp2
import time
from machine import Pin

# ==============================================================================
# PIO PROGRAMM: 1-Wire Treiber
# ==============================================================================
# Timing-Basis: 1 MHz (1 Zyklus = 1 µs)
#
# Besonderheiten:
# - Reset-Timing (>480us) wird durch Schleifen mit längeren Delays erreicht,
#   da der 'set' Befehl maximal den Wert 31 annehmen kann.
# - Synchronisation: Jede Schreib-Operation (auch 'Write 0') schiebt ein
#   Dummy-Byte in den Eingangspuffer. Python muss dieses immer abholen.
# ==============================================================================

@rp2.asm_pio(
    set_init=rp2.PIO.OUT_LOW,
    in_shiftdir=rp2.PIO.SHIFT_RIGHT, 
    autopush=True, 
    push_thresh=8,
    out_shiftdir=rp2.PIO.SHIFT_RIGHT, 
    autopull=True, 
    pull_thresh=8
)
def onewire():
    # --- RESET SEQUENCE ---
    label("reset")
    
    # 1. Master Reset Pulse (Low) -> Ziel: 500 us
    # Loop: 1 cyc (jmp) + 19 cyc (delay) = 20 us pro Durchlauf.
    # 25 Durchläufe * 20 us = 500 us.
    set(pindirs, 1)         # 1 cyc: Drive Low
    set(x, 24)      [0]     # 1 cyc: Setup (x=24 resultiert in 25 Loops)
    label("reset_wait_low")
    jmp(x_dec, "reset_wait_low") [19] 
    
    # 2. Release & Wait (High-Z) -> Ziel: 70 us (Sample Point)
    # Loop: 1 cyc (jmp) + 6 cyc (delay) = 7 us pro Durchlauf.
    # 10 Durchläufe * 7 us = 70 us.
    set(pindirs, 0)         # 1 cyc: Release Bus
    set(x, 9)       [5]     # 1 cyc + 5 delay = 6us Setup
    label("reset_wait_high")
    jmp(x_dec, "reset_wait_high") [6]
    
    # 3. Sampling
    mov(isr, pins)          # Snapshot aller Pins in das ISR
    push()                  # Ergebnis sofort in den FIFO pushen
    
    # 4. Recovery Time -> Ziel: ca. 400 us
    # Loop: 20 us pro Durchlauf.
    set(x, 19)      [1]     
    label("reset_finish")
    jmp(x_dec, "reset_finish") [19] 

    # --- BIT LOOP (Datenübertragung) ---
    wrap_target()
    label("fetch_bit")
    out(x, 1)               # 1 Bit vom Python-Buffer holen
    
    # Start Slot (Immer 1us Low am Anfang)
    set(pindirs, 1) [0]     
    jmp(not_x, "write_0")   [4] # Wenn Bit 0 ist, springe. Delay macht das Timing passend.
    
    # --- WRITE 1 / READ SLOT ---
    # Bus war kurz Low, jetzt loslassen.
    # Slave sampelt bei ca. 15-30us. Wir lesen bei 15us.
    set(pindirs, 0) [8]     # Release
    in_(pins, 1)    [5]     # Sample Input -> PUSH to FIFO
                            
    set(x, 2)       [10]    # Warten bis Slot-Ende
    label("w1_wait")
    jmp(x_dec, "w1_wait") [10]
    jmp("fetch_bit")
    
    # --- WRITE 0 SLOT ---
    # Bus für 60us Low halten.
    label("write_0")
    set(x, 5)       [8]     
    label("w0_loop")
    jmp(x_dec, "w0_loop") [8] 
    
    set(pindirs, 0) [2]     # Release
    in_(null, 1)            # WICHTIG: Dummy-Zero pushen für FIFO-Sync!
    wrap()


class OneWire:
    # Standard 1-Wire Befehle
    SEARCH_ROM = 0xF0
    MATCH_ROM = 0x55
    SKIP_ROM = 0xCC
    CONVERT_T = 0x44
    READ_SCRATCHPAD = 0xBE

    def __init__(self, pin_num, state_machine_id=0):
        # Pin Init: INPUT mit PullUp (Idle High), um Bus-Blockade zu vermeiden
        self.pin = Pin(pin_num, Pin.IN, Pin.PULL_UP)
        self.pin_num = pin_num
        self.pin.value(0) # Vorbereitung: Output-Register auf Low
        
        self.sm_id = state_machine_id
        self.sm = None
        self._bits = 8 # Aktueller Modus (1-Bit oder 8-Bit)
        self._init_sm(bits=8)

    def _init_sm(self, bits):
        """Initialisiert die State Machine neu (Reset PC=0)."""
        self._bits = bits
        if self.sm:
            self.sm.active(0)
            del self.sm
            
        self.sm = rp2.StateMachine(
            self.sm_id, 
            onewire, 
            freq=1_000_000,     # 1 MHz = 1us Zykluszeit
            set_base=self.pin,
            in_base=self.pin,
            push_thresh=bits,
            pull_thresh=bits
        )
        self.sm.active(1)
        self.sm.exec("set(pindirs, 0)") # Sicherstellen: Input Mode

    def _put_blocking(self, data):
        """Wartet, bis Platz im Sendepuffer ist."""
        while self.sm.tx_fifo() == 4: pass 
        self.sm.put(data)

    def _get_blocking(self):
        """Wartet auf Daten im Empfangspuffer."""
        while self.sm.rx_fifo() == 0: pass
        return self.sm.get()

    def reset(self):
        """
        Führt Master Reset durch.
        Return: True = Gerät erkannt (Presence Pulse), False = Kein Gerät.
        """
        self._init_sm(self._bits)
        val = self._get_blocking()
        # mov(isr, pins) liest alle Pins. Wir filtern unseren Pin heraus.
        # Wenn Pin == 0 (Low), hat ein Slave geantwortet.
        return ((val >> self.pin_num) & 1) == 0

    def write_byte(self, data):
        """Schreibt ein Byte und verwirft das generierte Echo."""
        self._put_blocking(data)
        self._get_blocking()

    def read_byte(self):
        """Liest ein Byte (sendet 0xFF)."""
        self._put_blocking(0xFF)
        val = self._get_blocking()
        return (val >> 24) & 0xFF

    def rom_search(self):
        """Findet alle 64-Bit ROM Codes am Bus."""
        found_roms = []
        rom_code = 0
        last_discrepancy = -1
        finished = False

        self._init_sm(bits=1) # 1-Bit Modus für Search

        try:
            while not finished:
                if not self.reset():
                    return []

                # Befehl senden (Bitweise)
                for i in range(8):
                    bit = (self.SEARCH_ROM >> i) & 1
                    self._put_blocking(bit)
                    self._get_blocking()

                direction = 0
                current_rom = 0
                discrepancy_marker = -1
                
                for i in range(64):
                    # 1. Bit lesen
                    self._put_blocking(1)
                    val = self._get_blocking()
                    b1 = 1 if (val & 0x80000000) else 0
                    
                    # 2. Komplement lesen
                    self._put_blocking(1)
                    val = self._get_blocking()
                    b2 = 1 if (val & 0x80000000) else 0
                    
                    if b1 == 1 and b2 == 1: 
                        return found_roms # Fehler: Keine Antwort
                    
                    if b1 != b2:
                        direction = b1
                    else: 
                        # Kollision
                        if i == last_discrepancy:
                            direction = 1
                        elif i > last_discrepancy:
                            direction = 0
                        else:
                            direction = (rom_code >> i) & 1
                        
                        if direction == 0:
                            discrepancy_marker = i

                    # Richtung schreiben
                    self._put_blocking(direction)
                    self._get_blocking()
                    
                    if direction:
                        current_rom |= (1 << i)

                rom_code = current_rom
                found_roms.append(rom_code)
                
                last_discrepancy = discrepancy_marker
                if last_discrepancy == -1:
                    finished = True
        finally:
            self._init_sm(bits=8) # Zurück in den 8-Bit Modus
            
        return found_roms

    @staticmethod
    def crc8(data):
        """Berechnet CRC-8 (Maxim/Dallas Polynom)."""
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x01:
                    crc = (crc >> 1) ^ 0x8C
                else:
                    crc >>= 1
        return crc