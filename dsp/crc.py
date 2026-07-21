"""CRC calculation for Aurora frames."""


CRC16_POLYNOMIAL = 0x1021
CRC16_INITIAL = 0xFFFF


def crc16_ccitt(data: bytes) -> int:
    """Return the CRC-16/CCITT-FALSE value for *data*."""
    crc = CRC16_INITIAL
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC16_POLYNOMIAL) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def verify_crc16(data: bytes, expected_crc: int) -> bool:
    """Return whether *data* matches an expected CRC-16 value."""
    return crc16_ccitt(data) == expected_crc
