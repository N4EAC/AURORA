"""Compact native reports describing a previously received Aurora frame."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from dsp.core import EncodedTransmission, encode_payload
from dsp.framing import Frame, build_frame
from modem.ax25 import Ax25Address
from modem.bootstrap import AirTransmission, FRAME_TYPE_RECEPTION_REPORT, build_air_transmission
from modem.mode_definition import AURORA_ROBUST_MODE, ModeDefinition


AURORA_FLAG_RECEPTION_REPORT = 0x04
REPORT_MAGIC = b"AR"
REPORT_VERSION = 1
_FORMAT = ">2sBIBhhhH"
_SIZE = struct.calcsize(_FORMAT)


@dataclass(frozen=True, slots=True)
class ReceptionReport:
    """Receiver measurements associated with one earlier frame ID."""

    reporter: str
    referenced_frame_id: int
    snr_db: float
    frequency_offset_hz: float
    timing_offset_samples: float
    fec_corrections: int


def build_reception_report(report: ReceptionReport) -> bytes:
    """Serialize measurements using bounded fixed-point integers."""
    callsign = str(Ax25Address.parse(report.reporter)).encode("ascii")
    if not 0 <= report.referenced_frame_id <= 0xFFFFFFFF:
        raise ValueError("Referenced frame ID is invalid")
    values = (
        round(report.snr_db * 10),
        round(report.frequency_offset_hz * 10),
        round(report.timing_offset_samples * 10),
    )
    if any(not -32_768 <= value <= 32_767 for value in values):
        raise ValueError("Reception measurement exceeds its encoded range")
    if not 0 <= report.fec_corrections <= 65_535:
        raise ValueError("FEC correction count is invalid")
    return struct.pack(
        _FORMAT,
        REPORT_MAGIC,
        REPORT_VERSION,
        report.referenced_frame_id,
        len(callsign),
        *values,
        report.fec_corrections,
    ) + callsign


def parse_reception_report(encoded: bytes) -> ReceptionReport:
    """Decode one compact reception report."""
    if len(encoded) < _SIZE:
        raise ValueError("Reception report is too short")
    magic, version, frame_id, call_size, snr, offset, timing, corrections = struct.unpack(
        _FORMAT, encoded[:_SIZE]
    )
    if magic != REPORT_MAGIC or version != REPORT_VERSION:
        raise ValueError("Reception report identity is invalid")
    if len(encoded) != _SIZE + call_size:
        raise ValueError("Reception report length is invalid")
    try:
        callsign = encoded[_SIZE:].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Reception report callsign is invalid") from error
    return ReceptionReport(
        str(Ax25Address.parse(callsign)),
        frame_id,
        snr / 10.0,
        offset / 10.0,
        timing / 10.0,
        corrections,
    )


def encode_reception_report(
    report: ReceptionReport,
    *,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> EncodedTransmission:
    """Protect a native reception report."""
    payload = build_reception_report(report)
    return encode_payload(
        payload,
        flags=AURORA_FLAG_RECEPTION_REPORT,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )


def encode_reception_report_air_transmission(
    report: ReceptionReport,
    *,
    frame_id: int,
    mode: ModeDefinition = AURORA_ROBUST_MODE,
) -> AirTransmission:
    """Build a bootstrapped native reception-report transmission."""
    native = build_reception_report(report)
    payload = encode_payload(
        native,
        flags=AURORA_FLAG_RECEPTION_REPORT,
        modulation=mode.modulation,
        interleaver_columns=mode.interleaver_columns,
    )
    return build_air_transmission(
        payload,
        payload_size=len(build_frame(native, AURORA_FLAG_RECEPTION_REPORT)),
        frame_type=FRAME_TYPE_RECEPTION_REPORT,
        frame_id=frame_id,
        mode=mode,
    )


def decode_reception_report(frame: Frame) -> ReceptionReport:
    """Decode a report from one CRC-valid Aurora frame."""
    if frame.flags != AURORA_FLAG_RECEPTION_REPORT:
        raise ValueError("Aurora frame does not contain a reception report")
    return parse_reception_report(frame.payload)
