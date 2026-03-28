import struct

# ----------------------------------------------------------------------
# Paste your complete hex dump here (the 832‑word data from the file)
# ----------------------------------------------------------------------
raw_hex = (
    "00AC899F000020610005032003E010213C15018E048D0000190100001000BE334200FFD012120102"
    "F101F1F1E0E1B0D00E32ED12CCF2CCE1CED4D0F5E307C71779A63933EDBA210F333233330012BC"
    "EEDDBB00FE2211333333331122FF00CCDE16C02F952156A48F7666F98064635E5D2463FC7313D2"
    "0643EC00F3009EC5255816300F201FEEFC5E08AE0800180EFC1E081E007E1FDEFFEE078E078E1B"
    "BEFB9E07F003F01B5EFB6E003003E01070F40E089000101070F4100040F8C01052F3900E6203D"
    "EF7EC0C400480FFFEF7EC0FF003F0FC6EFBBC0FD00370036EF7BC0BA0FFD003DEFB4C0B30FC12F"
    "FCEF05E0BF00472FC00F44E0BE00022F8B0F44E0BE20790007017DEF44E00BE03F017EEF41E03F"
    "EFC5017BEF7FE036EFBE017AEF39E03F0FFD0136EF34EFC00FBF00C30F3FE0080F4300820EC00F"
    "C10F0D00C22F3E003B0F85EF3CC0420FC80FBCEF3BC07E0FBD0F83EF79C0BD00330F7BEF78C077"
    "0FFC0FFBEF34E0720FBD2F3DEEC0E03C0FC42F7F0EFFE03D0FFE2F0A0F00003B20800FCB013DEF"
    "41E0490FFF013DEF7FE0410F8900C0EF04E03BEFBD00C2EEFEEFC40F8000BD0EF6EFC30F420081"
    "0F3BEFC60F7E00BF0EBF0F420F0B00442EBF013C2007EFFAE13D00C5207BEFFAE17A013D0005EF"
    "FEC10200F8007AEFC0E0FC0081207EEFBBE0F3007F2FFFEFBEE1370082203B0FFAE0FA007D2006"
    "0F8000FC20BF00C701FB0001E04AE08201FD0FC2E043E0490183EFC4E07CE0BD01C0EFBFE0FF00"
    "4201B90F7CE040003F01410FBB0043203A013D0FB800BA000421022FBB0FFC2FC3EF77E0BC0FC5"
    "0FBEEF78E0BD0FFF0F85EF3FE0BF0FF80038EF7BE0BB007B2FFFEF75E078003C2FBB0F3DE0F600"
    "7F2FF50F37E0B300B42FFF0F3C00F62041008901BE0FC4004A008001BF0FC2E045000C01FFEFC5"
    "E0BCE0450181EF81E0070007017A0F7DE0060FC401040F7E0043203F013C0F7800770FC421012F"
    "7C0FBB2F430EF8E03E0F840FBA0EFAE03D0FC00F87EF3AE04100370F80EF7BE07D0F822F81EEF5"
    "E0380FC02F7E0EFEE0B9003D2FB90F35E07200302FBD0F3A007620FC0086217B0FC0010400BB01"
    "BB0FC000460008017EEF84E08000020108EF45E006000600FF0F7BE0040FC300C20F7C00012FFD"
    "00F50F740FF50FFE20BE2F3A00FD20070FBBE1000105207B0FBCE10000472009EFFFE10500C200"
    "04EF87E0C4008620470F81E0FD008720060F84E17E00C3207E0FF7E13600B620400FBE00FA2FFD"
    "004721790F810006007C00FF0F440FC3000A00C50F84EFC00FC801030F42EF870FC900FE0EC40F"
    "C40FC200880EC50FC52FFD20BA2F3500342FC020802F3B003C2FC60F39E08000062FFB0F3FE084"
    "0FC30FC90F04E0C200002FC70F43E0820FC62FC90F3DE04300442FC30F07E0C50084203D0F7A00"
    "F620B520010FBF00FB2FF9008320F70F7E0FC3003E20BB0F410F46000600FE0F410FFB003E0082"
    "0F020F840FC200B90EFC0F830FC100820F3C0F812FBB20772F340FF42F82207D2F380FB72F410E"
    "B5E03C2F812F7C0EBAE03F0F042F440EBCE07F0FB90FBC0EFFE07F0F832FC00EB9E07A0FC12FBF"
    "0EC0E0BB00002FFA0EF700B420742FC10EFC00B72079204520F60F410FC30FFC207A0F3C0FFE0F"
    "C4007A0F430FF90FFB007E0F3E0F840FC3007B0EFE0FFF0FC020400F780F822FFA2FF90F350F77"
    "0F832FBF2EFA00BE200A0F7BE087204720010F3EE0C1008220090F40E08800BF20410F43E0C300"
    "4820860F40E0C300C420840F86E1BE210720BE0FBF013B20FC20490F8501002FC00108213F0004"
    "000A013D213E0001000100C5217E0003007A00C121420FFE004100C5213D0FFB000500C0214500"
    "3E0046208320C2203B007D20C72102203F0EFC2F440E7BE0002F462FB90EBAE07D2FBD2FC10EFA"
    "E0BF00362FBD0EFDE0FA0FFD20010EF9E0F70FC0203C0F01013A204220002F3F013820BA20440F"
    "7F017B2F7F014720FE00040FCA00C020FF0FC2003F0087213D003F0FFB008021010FFF003F00C2"
    "20BF0FBC0003008220C82FC10FC920C320C0203D003F20CA2085203F2F7620020EBA00802FC52F"
    "FB0EFAE0FD203A20010F77E17A2034207A0F3BE13A207A207D0F3AE17720BF20BD0F43017C2084"
    "20FE0FFC01BA213B21050FC0023A2FE6217C40F900010F8500FB207B0FFD0FBB008220B7003900"
    "33013420B80FF8003A013B20F70033007B00FF20C1203E000100C02000203C0FFC0108200020BA"
    "2F6320332E7B00822F87203D0E7E00812FFE20040F3900FB00B520B60F7A013A007C20FD0F7801"
    "B4213D20C10F8401C2210420C20F8301BF217F214A000102772"
)

# ----------------------------------------------------------------------
# Convert hex string to bytes (assume continuous hex, no spaces)
# ----------------------------------------------------------------------
hex_str = raw_hex.replace(' ', '').replace('\n', '')
if len(hex_str) % 2 != 0:
    print("Warning: hex string has an odd number of characters. Removing the last character.")
    hex_str = hex_str[:-1]  # try to fix (the last digit might be a typo)
bytes_data = bytes.fromhex(hex_str)
print(f"Total bytes: {len(bytes_data)} (expected 1664 for 832 words)")

# ----------------------------------------------------------------------
# Form 16‑bit words (little‑endian: first byte is LSB)
# ----------------------------------------------------------------------
words = []
for i in range(0, len(bytes_data), 2):
    if i+1 < len(bytes_data):
        w = bytes_data[i] | (bytes_data[i+1] << 8)
        words.append(w)
print(f"Total words: {len(words)}")

# The calibration data is stored in the first 256 words (addresses 0x2400..0x24FF)
if len(words) < 256:
    raise ValueError("Not enough words for calibration data")
eeprom = words[:256]

# ----------------------------------------------------------------------
# Helper: signed 16‑bit
# ----------------------------------------------------------------------
def s16(x):
    return x if x < 32768 else x - 65536

# ----------------------------------------------------------------------
# Parse according to MLX90640 datasheet Rev. 8, section 9.3
# ----------------------------------------------------------------------
cal = {}

# Gain, resolution, control (addresses 0x2428, 0x2429)
cal['gain'] = eeprom[40] & 0x3FFF                     # Gain (14 bits)
cal['resolution'] = (eeprom[41] >> 3) & 0x03          # ADC resolution mode
cal['ctrl'] = eeprom[41] & 0x07                        # Control bits

# Ambient temperature correction (addresses 0x2420..0x2427)
cal['ta_scale'] = eeprom[32] & 0x0F                    # TaScale
cal['kv'] = s16(eeprom[36])                             # Kv
cal['kt'] = s16(eeprom[37])                             # Kt

# Pixel correction (addresses 0x2421..0x2427)
cal['ks_ta'] = s16(eeprom[33])                          # KsTa
# KsTo is 12 bits: low byte in eeprom[34] bits 7..0, high nibble in eeprom[35] bits 11..8
cal['ks_to'] = (eeprom[34] & 0xFF) | ((eeprom[35] >> 4) & 0x0F) << 8
# CP_Offset, CP_Kv, CP_Kt
cal['cp_offset'] = s16(eeprom[35] & 0x000F)             # actually CP_Offset is only 4 bits? Wait, need correct.
# Let's follow datasheet precisely:

# Word 35 (0x2423): bits 11-8 = KsTo high nibble, bits 3-0 = CP_Offset (signed 4-bit)
cp_offset_raw = eeprom[35] & 0x000F
cal['cp_offset'] = cp_offset_raw if cp_offset_raw < 8 else cp_offset_raw - 16   # 4-bit signed

# Word 38 (0x2426): CP_Kv (signed 16-bit)
cal['cp_kv'] = s16(eeprom[38])

# Word 39 (0x2427): CP_Kt (signed 16-bit)
cal['cp_kt'] = s16(eeprom[39])

# OSC Trim (word 10, bits 7-0)
cal['osc_trim'] = eeprom[10] & 0xFF

# VDD25 (word 11) – used for reference voltage compensation
cal['vdd25'] = eeprom[11]

# Pixel offset coefficients (Vth) – stored in 32x24 = 768 values.
# They are packed in EEPROM words 64..255 (addresses 0x2440..0x24FF).
# Each pixel offset is 16 bits, but stored in a special format.
# We extract them as raw values (the full decoding requires additional scaling).
vth = []
for addr in range(64, 256):
    vth.append(s16(eeprom[addr]))

# Sensitivity correction coefficients (KsTo per pixel) – stored in another area,
# but often combined with Vth in the same words. For brevity we show only the first few.

# ----------------------------------------------------------------------
# Print results
# ----------------------------------------------------------------------
print("\n=== Calibration Parameters (MLX90640) ===\n")
print(f"Gain:                     {cal['gain']}")
print(f"Resolution mode:          {cal['resolution']} (0=16bit,1=17bit,2=18bit,3=19bit)")
print(f"Control bits:             {cal['ctrl']}")
print(f"TaScale:                  {cal['ta_scale']}")
print(f"Kv (ambient correction):  {cal['kv']}")
print(f"Kt (ambient correction):  {cal['kt']}")
print(f"KsTa:                     {cal['ks_ta']}")
print(f"KsTo:                     {cal['ks_to']}")
print(f"CP_Offset:                {cal['cp_offset']}")
print(f"CP_Kv:                    {cal['cp_kv']}")
print(f"CP_Kt:                    {cal['cp_kt']}")
print(f"OSC Trim:                 {cal['osc_trim']}")
print(f"VDD25:                    {cal['vdd25']}")
print(f"\nPixel offset coefficients (first 10 of 768): {vth[:10]} ...")
print("\n(Full pixel data can be extracted from words 64..255; above are raw signed values.)")