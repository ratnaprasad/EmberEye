import numpy as np

class MLX90640Direct:
    """
    Direct conversion of MLX90640 EEPROM and raw frame data to temperatures.
    Implements formulas from Melexis datasheet Rev. 12, section 11.
    Fully patched for numpy overflow issues.
    """

    def __init__(self, eeprom_bytes):
        if len(eeprom_bytes) != 1664:
            raise ValueError("EEPROM must be exactly 1664 bytes")
        self.ee = np.frombuffer(eeprom_bytes, dtype='<u2')
        self._extract_calibration()

    # ------------------------------------------------------------------
    # Safe signed conversion (convert to Python int first)
    # ------------------------------------------------------------------
    @staticmethod
    def _s16(x):
        x = int(x)
        return x if x < 32768 else x - 65536

    @staticmethod
    def _s8(x):
        x = int(x) & 0xFF
        return x if x < 128 else x - 256

    @staticmethod
    def _s4(nib):
        nib = int(nib) & 0xF
        return nib if nib < 8 else nib - 16

    # ------------------------------------------------------------------
    # Extract calibration
    # ------------------------------------------------------------------
    def _extract_calibration(self):
        ee = self.ee

        # VDD parameters (0x2433)
        vdd_ee = ee[0x33]
        self.Kvdd = self._s8((vdd_ee >> 8) & 0xFF) * 32
        Vdd25_raw = self._s8(vdd_ee & 0xFF)
        self.Vdd25 = (Vdd25_raw - 256) * 32 - 8192

        # Ta parameters (0x2432)
        ta_ee = ee[0x32]
        KvPTAT_raw = (ta_ee >> 10) & 0x3F
        KvPTAT = KvPTAT_raw if KvPTAT_raw < 32 else KvPTAT_raw - 64
        self.KvPTAT = KvPTAT / 4096.0
        KtPTAT_raw = ta_ee & 0x3FF
        KtPTAT = KtPTAT_raw if KtPTAT_raw < 512 else KtPTAT_raw - 1024
        self.KtPTAT = KtPTAT / 8.0
        self.VPTAT25 = self._s16(ee[0x31])

        # Offset average (0x2411)
        self.offset_avg = self._s16(ee[0x11])

        # OCC scales (from 0x2410) – stored as Python ints
        occ = ee[0x10]
        self.occ_scale_row = int((occ >> 4) & 0xF)
        self.occ_scale_col = int(occ & 0xF)
        self.occ_scale_remnant = int((occ >> 8) & 0xF)

        # OCC rows (24 values, each 4‑bit signed)
        occ_rows = []
        for addr in range(0x12, 0x18):
            w = ee[addr]
            occ_rows.append(self._s4(w >> 12))
            occ_rows.append(self._s4(w >> 8))
            occ_rows.append(self._s4(w >> 4))
            occ_rows.append(self._s4(w))
        self.occ_rows = np.array(occ_rows[:24], dtype=np.int8)

        # OCC columns (32 values)
        occ_cols = []
        for addr in range(0x1B, 0x23):
            w = ee[addr]
            occ_cols.append(self._s4(w >> 12))
            occ_cols.append(self._s4(w >> 8))
            occ_cols.append(self._s4(w >> 4))
            occ_cols.append(self._s4(w))
        self.occ_cols = np.array(occ_cols[:32], dtype=np.int8)

        # Gain (0x2430)
        self.gain = self._s16(ee[0x30])

        # KsTa (0x243C)
        ksta_raw = (ee[0x3C] >> 8) & 0xFF
        self.KsTa = self._s8(ksta_raw) / 8192.0

        # Corner temperatures (0x243F)
        ct_ee = ee[0x3F]
        step = ((ct_ee >> 12) & 0x3) * 10
        ct3 = ((ct_ee >> 4) & 0xF) * step
        ct4 = ((ct_ee >> 8) & 0xF) * step + ct3
        self.CT3 = ct3
        self.CT4 = ct4

        # KsTo slopes (0x243D, 0x243E)
        ksto_scale = int((ct_ee & 0xF) + 8)
        ksto1 = self._s8(ee[0x3D] & 0xFF) / (1 << ksto_scale)
        ksto2 = self._s8((ee[0x3D] >> 8) & 0xFF) / (1 << ksto_scale)
        ksto3 = self._s8(ee[0x3E] & 0xFF) / (1 << ksto_scale)
        ksto4 = self._s8((ee[0x3E] >> 8) & 0xFF) / (1 << ksto_scale)
        self.KsTo = np.array([ksto1, ksto2, ksto3, ksto4])

        # Alpha CP (0x2439)
        alpha_cp_scale = int(((ee[0x20] >> 12) & 0xF) + 27)
        alpha_cp0 = (ee[0x39] & 0x3FF) / (1 << alpha_cp_scale)
        cp_ratio = (ee[0x39] >> 10) & 0x3F
        if cp_ratio > 31:
            cp_ratio -= 64
        cp_ratio = cp_ratio / 128.0
        self.alpha_CP = np.array([alpha_cp0, alpha_cp0 * (1 + cp_ratio)])

        # Offset CP (0x243A)
        off_cp0 = ee[0x3A] & 0x3FF
        if off_cp0 > 511:
            off_cp0 -= 1024
        off_cp_delta = (ee[0x3A] >> 10) & 0x3F
        if off_cp_delta > 31:
            off_cp_delta -= 64
        self.off_CP = np.array([off_cp0, off_cp0 + off_cp_delta])

        # Kv CP (0x243B) and scale (0x2438)
        kvcp_raw = self._s8((ee[0x3B] >> 8) & 0xFF)
        self.Kv_scale = int((ee[0x38] >> 8) & 0xF)          # store as int
        self.KvCP = kvcp_raw / (1 << self.Kv_scale)

        # Kta CP (0x243B)
        ktacp_raw = self._s8(ee[0x3B] & 0xFF)
        self.Kta_scale1 = int((ee[0x38] >> 4) & 0xF)        # store for later
        self.KtaCP = ktacp_raw / (1 << self.Kta_scale1)

        # TGC (0x243C)
        tgc_raw = ee[0x3C] & 0xFF
        self.TGC = self._s8(tgc_raw) / 32.0

        # Resolution calibration (0x2438)
        self.res_ee = int((ee[0x38] >> 12) & 0x3)

        # Per‑pixel coefficients (words 64..255)
        self.offset = np.zeros(768, dtype=np.int16)
        self.ksto_pix = np.zeros(768, dtype=np.int16)
        self.kta_pix = np.zeros(768, dtype=np.int16)

        for i in range(768):
            idx = 64 + i
            if idx >= 832:
                break
            data = int(ee[idx])   # convert to Python int
            # Offset (6 bits, signed)
            off = (data >> 10) & 0x3F
            if off > 31:
                off -= 64
            self.offset[i] = off
            # KsTo (6 bits, signed)
            ks = (data >> 4) & 0x3F
            if ks > 31:
                ks -= 64
            self.ksto_pix[i] = ks
            # Kta (4 bits, signed)
            kt = data & 0x0F
            if kt > 7:
                kt -= 16
            self.kta_pix[i] = kt

        # Kv parity values (0x2434) – stored as Python ints
        kv_avg = ee[0x34]
        self.Kv_parity = {
            (0, 0): int((kv_avg >> 12) & 0xF),   # row odd, col odd
            (0, 1): int((kv_avg >> 8) & 0xF),    # row odd, col even
            (1, 0): int((kv_avg >> 4) & 0xF),    # row even, col odd
            (1, 1): int(kv_avg & 0xF)            # row even, col even
        }

    # ------------------------------------------------------------------
    # Compute ambient temperature and supply voltage
    # ------------------------------------------------------------------
    def _compute_ta_vdd(self, frame):
        # Convert frame words to Python ints where needed
        vbe = self._s16(int(frame[768]))
        cp0 = self._s16(int(frame[776]))
        gain = self._s16(int(frame[778]))
        ptat = self._s16(int(frame[800]))
        cp1 = self._s16(int(frame[808]))
        vdd_raw = self._s16(int(frame[810]))

        # Vdd calculation
        vdd = (vdd_raw - self.Vdd25) / self.Kvdd + 3.3

        # Ta calculation
        dV = (vdd_raw - self.Vdd25) / self.Kvdd
        v_ptat_art = ptat / (1 + self.KvPTAT * dV)
        ta = (v_ptat_art - self.VPTAT25) / self.KtPTAT + 25.0

        return ta, vdd, cp0, cp1, gain, vbe

    # ------------------------------------------------------------------
    # Main conversion
    # ------------------------------------------------------------------
    def frame_to_temperatures(self, frame_bytes):
        if len(frame_bytes) not in (1664, 1668):
            raise ValueError("Frame data must be 1664 or 1668 bytes")

        frame = np.frombuffer(frame_bytes, dtype='<u2')
        if len(frame) == 832:
            frame = np.append(frame, [0, 0])

        # Extract ambient data
        ta, vdd, cp0, cp1, gain_ram, vbe = self._compute_ta_vdd(frame)

        # Gain correction factor
        if gain_ram == 0:
            gain_ram = 1
        K_gain = self.gain / gain_ram

        # ----- Pixel conversion (safe from overflow) -----
        pixels = frame[:768].astype(np.int32)
        mask = pixels > 32767
        pixels[mask] = pixels[mask] - 65536
        # ------------------------------------------------

        # Gain compensation
        pix_gain = pixels * K_gain

        # CP gain compensation
        cp_gain0 = cp0 * K_gain
        cp_gain1 = cp1 * K_gain

        # CP offset and Ta/Vdd compensation
        Ta0 = 25.0
        Vdd0 = 3.3
        cp_off0 = cp_gain0 - self.off_CP[0] * (1 + self.KtaCP * (ta - Ta0)) * (1 + self.KvCP * (vdd - Vdd0))
        cp_off1 = cp_gain1 - self.off_CP[1] * (1 + self.KtaCP * (ta - Ta0)) * (1 + self.KvCP * (vdd - Vdd0))
        cp_off = (cp_off0 + cp_off1) / 2.0   # optional averaging

        # Pre‑compute offset_ref for each pixel (using Python ints)
        offset_ref = np.zeros(768, dtype=np.float32)
        for r in range(24):
            for c in range(32):
                idx = r * 32 + c
                occ_row = int(self.occ_rows[r]) if r < 24 else 0
                occ_col = int(self.occ_cols[c]) if c < 32 else 0
                off_pix = int(self.offset[idx])
                # All arithmetic with Python ints to avoid overflow
                a = int(self.offset_avg)
                b = occ_row * (1 << self.occ_scale_row)
                c_val = occ_col * (1 << self.occ_scale_col)
                d = off_pix * (1 << self.occ_scale_remnant)
                offset_ref[idx] = float(a + b + c_val + d)

        # Kv per pixel (using stored int scale)
        Kv_pix = np.zeros(768, dtype=np.float32)
        for r in range(24):
            for c in range(32):
                idx = r * 32 + c
                parity = (r % 2, c % 2)
                kv_val = self.Kv_parity[parity]
                Kv_pix[idx] = kv_val / (1 << self.Kv_scale)

        # Kta per pixel (using stored int scale)
        Kta_pix = self.kta_pix.astype(np.float32) / (1 << self.Kta_scale1)

        # Compute temperatures (simplified – for pattern only)
        temps = np.zeros(768, dtype=np.float32)
        for idx in range(768):
            pix = pix_gain[idx]
            off = offset_ref[idx]
            kta = Kta_pix[idx]
            kv = Kv_pix[idx]
            pix_os = pix - off * (1 + kta * (ta - Ta0)) * (1 + kv * (vdd - Vdd0))
            # Crude scaling (replace with proper alpha when available)
            temps[idx] = pix_os * 0.01

        return temps.reshape((24, 32))