import logging
from typing import Optional, Any

logger = logging.getLogger("RFDriver")

try:
    import rflib  # type: ignore
except Exception:  # pragma: no cover
    rflib = None

# CC1110Fx / CC1111Fx XDATA addresses (SWRS033H)
FREND0_ADDR = 0xDF1B      # FREND0 - Front End TX Configuration
PA_TABLE0_ADDR = 0xDF2E   # PA_TABLE0..7: 0xDF2E down to 0xDF27

# Human-friendly TX power lookup table (target dBm -> PATABLE value),
# derived from TI recommended settings by band.
#
# Notes:
# - These codes are NOT "hex = dBm". They are PATABLE register values.
# - The same dBm target uses different codes at different frequency bands.
# - In ASK/OOK, PATABLE[0] is used for '0' level and PA_POWER selects the '1' level index.
POWER_TABLE = {
    315: {-30: 0x12, -20: 0x0D, -15: 0x1C, -10: 0x34, -5: 0x2B, 0: 0x51, 5: 0x85, 7: 0xCB, 10: 0xC2},
    433: {-30: 0x12, -20: 0x0E, -15: 0x1D, -10: 0x34, -5: 0x2C, 0: 0x60, 5: 0x84, 7: 0xC8, 10: 0xC0},
    868: {-30: 0x03, -20: 0x0E, -15: 0x1E, -10: 0x27, -5: 0x8F, 0: 0x50, 5: 0x84, 7: 0xCB, 10: 0xC2},
    915: {-30: 0x03, -20: 0x0D, -15: 0x1D, -10: 0x26, -5: 0x57, 0: 0x8E, 5: 0x83, 7: 0xC7, 10: 0xC0},
}

VALID_DBM = sorted({k for band in POWER_TABLE.values() for k in band.keys()})


def _parse_int(value: Any) -> Optional[int]:
    """Parse an int that may be: int, '123', '0x7f', or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(s, 0)
        except ValueError:
            return None
    return None


def _parse_patable(value: Any) -> Optional[list[int]]:
    """Parse PATABLE config.

    Accepts:
      - int or "0xC0" -> [0xC0]
      - "0x00,0x03,..." -> [0x00, 0x03, ...]
      - [0, "0xC0", ...] -> list[int]
    """
    if value is None:
        return None

    if isinstance(value, int):
        return [value & 0xFF]

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if "," in s:
            out: list[int] = []
            for part in [p.strip() for p in s.split(",") if p.strip()]:
                v = _parse_int(part)
                if v is None:
                    return None
                out.append(v & 0xFF)
            return out or None
        v = _parse_int(s)
        return [v & 0xFF] if v is not None else None

    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            v = _parse_int(item)
            if v is None:
                return None
            out.append(v & 0xFF)
        return out or None

    return None


def _infer_band(freq_hz: int) -> int:
    """Infer which datasheet band bucket to use based on TX frequency."""
    # crude but effective bucket selection
    if freq_hz < 380_000_000:
        return 315
    if freq_hz < 600_000_000:
        return 433
    if freq_hz < 900_000_000:
        return 868
    return 915


def _select_band(freq_hz: int, override: Any) -> int:
    if override is None:
        return _infer_band(freq_hz)
    if isinstance(override, str):
        s = override.strip().lower()
        if not s or s == "auto":
            return _infer_band(freq_hz)
        ov = _parse_int(s)
        if ov in (315, 433, 868, 915):
            return int(ov)
        return _infer_band(freq_hz)
    if isinstance(override, int) and override in (315, 433, 868, 915):
        return int(override)
    return _infer_band(freq_hz)


def _lookup_power_code(band: int, target_dbm: int) -> Optional[int]:
    band_map = POWER_TABLE.get(band)
    if not band_map:
        return None
    return band_map.get(int(target_dbm))


class Radio:
    """Thin wrapper around rflib.RfCat with a stable transmit() API."""

    def __init__(self):
        if rflib is None:
            raise ImportError("rflib is not available (RfCat not installed)")

        try:
            self.d = rflib.RfCat()
            self.d.setModeIDLE()
            logger.info("RF Device Initialized")
        except Exception as e:
            logger.critical(f"Could not initialize RF device: {e}")
            raise

    # ---------------------------------------------------------------------
    # Optional XDATA access (peek/poke). Used for deterministic FREND0/PATABLE.
    # ---------------------------------------------------------------------
    def _xdata_read(self, addr: int, size: int = 1) -> Optional[bytes]:
        """Read CC111x XDATA (best-effort, compatible with Python-2-style rflib).

        Depending on the rflib/RFCat build, peek() may return:
          - bytes/bytearray
          - list/tuple of ints
          - a latin-1 `str` (Python 2 "byte string")
        """
        if not hasattr(self.d, "peek"):
            return None

        try:
            raw = self.d.peek(addr, size)
        except Exception:
            return None

        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        if isinstance(raw, str):
            return raw.encode("latin-1", errors="ignore")

        try:
            return bytes(raw)
        except Exception:
            return None

    def _xdata_write(self, addr: int, data: bytes) -> bool:
        """Write CC111x XDATA (best-effort, compatible with Python-2-style rflib).

        Depending on the rflib/RFCat build, poke() may accept:
          - bytes/bytearray
          - list[int]
          - a latin-1 `str` (Python 2 "byte string")
        """
        if not hasattr(self.d, "poke"):
            return False

        candidates = [
            list(data),  # most portable
            data,        # ideal if supported
        ]
        try:
            candidates.append(data.decode("latin-1", errors="ignore"))
        except Exception:
            pass

        for payload in candidates:
            try:
                self.d.poke(addr, payload)
                return True
            except TypeError:
                continue
            except Exception:
                continue

        return False

    def _dump_power_regs(self, prefix: str = "") -> None:
        """Log FREND0 + PA_TABLE0..PA_TABLE7 (best-effort)."""
        try:
            fr = self._xdata_read(FREND0_ADDR, 1)
            frend0 = fr[0] if fr else None

            pt: list[Optional[int]] = []
            for i in range(8):
                b = self._xdata_read(PA_TABLE0_ADDR - i, 1)
                pt.append(b[0] if b else None)

            def hx(v: Optional[int]) -> str:
                return f"0x{v:02X}" if isinstance(v, int) else "None"

            logger.info(
                f"{prefix}Power regs: FREND0={hx(frend0)} PA_TABLE0..7=["
                + ", ".join(hx(v) for v in pt)
                + "]"
            )
        except Exception as e:
            logger.debug(f"Power regs dump failed: {e}")


    def _write_patable_index(self, index: int, value: int) -> None:
        if index < 0 or index > 7:
            raise ValueError("PATABLE index must be 0..7")
        addr = PA_TABLE0_ADDR - index
        ok = self._xdata_write(addr, bytes([value & 0xFF]))
        if not ok:
            raise RuntimeError("Unable to write PATABLE (poke() not available or failed)")

    def _set_frend0(self, pa_power: int, lodiv_buf_current_tx: Optional[int]) -> None:
        cur = self._xdata_read(FREND0_ADDR, 1)
        if cur is None:
            raise RuntimeError("FREND0 update requires firmware with peek()/poke() support")

        cur_val = cur[0]
        new_val = cur_val

        if lodiv_buf_current_tx is not None:
            if not (0 <= lodiv_buf_current_tx <= 3):
                raise ValueError("frend0_lodiv_buf_current_tx must be 0..3")
            new_val = (new_val & ~(0b11 << 4)) | ((lodiv_buf_current_tx & 0b11) << 4)

        if not (0 <= pa_power <= 7):
            raise ValueError("frend0_pa_power must be 0..7")
        new_val = (new_val & ~0b111) | (pa_power & 0b111)

        if new_val != cur_val:
            if not self._xdata_write(FREND0_ADDR, bytes([new_val])):
                raise RuntimeError("Unable to write FREND0 (poke() failed)")

    def _apply_manual_regs(
        self,
        modulation: str,
        frend0_pa_power: Any,
        frend0_lodiv_buf_current_tx: Any,
        patable: Any,
    ) -> None:
        """Deterministic register programming (FREND0 + PA_TABLE0..7)."""
        pa_power = _parse_int(frend0_pa_power)
        lo_div = _parse_int(frend0_lodiv_buf_current_tx)
        pt = _parse_patable(patable)

        if pa_power is None:
            # sensible default for ASK/OOK: index 0 is off, index 1 is on
            pa_power = 1

        self._set_frend0(pa_power=pa_power, lodiv_buf_current_tx=lo_div)

        if pt is None:
            logger.warning("manual power mode selected but 'patable' not provided; leaving PATABLE unchanged")
            return

        is_ask = str(modulation).upper() in ("ASK_OOK", "ASK", "OOK") or str(modulation).upper().startswith("ASK")

        # Single value -> treat as ON level; fill indices up to PA_POWER
        if len(pt) == 1:
            on_val = pt[0] & 0xFF

            if is_ask:
                # In ASK/OOK, index 0 is used for '0' level -> ensure it's off.
                self._write_patable_index(0, 0x00)
                start = 1
            else:
                start = 0

            for idx in range(start, pa_power + 1):
                self._write_patable_index(idx, on_val)

            self._dump_power_regs(prefix="Manual power applied: ") 
            return

        if len(pt) > 8:
            raise ValueError("patable list may have at most 8 entries (PA_TABLE0..PA_TABLE7)")

        for idx, v in enumerate(pt):
            self._write_patable_index(idx, v & 0xFF)
            
        self._dump_power_regs(prefix="Manual power applied: ")

    def _apply_smart_power(
        self,
        freq_hz: int,
        modulation: str,
        target_dbm: Any,
        band_override: Any,
        lodiv_buf_current_tx: Any,
    ) -> None:
        """Human-friendly mode: choose PATABLE from (band, dBm)."""
        t_dbm = _parse_int(target_dbm)
        if t_dbm is None:
            t_dbm = 0

        band = _select_band(freq_hz, band_override)
        code = _lookup_power_code(band, t_dbm)

        if code is None:
            logger.warning(
                f"Smart power: no table entry for band={band} target_dbm={t_dbm}. "
                f"Valid dBm values: {VALID_DBM}. Falling back to max power."
            )
            if hasattr(self.d, "setMaxPower"):
                self.d.setMaxPower()
            return

        # Prefer deterministic regs if firmware supports it; otherwise fall back to rflib helper.
        can_regs = hasattr(self.d, "peek") and hasattr(self.d, "poke")

        is_ask = str(modulation).upper() in ("ASK_OOK", "ASK", "OOK") or str(modulation).upper().startswith("ASK")

        if can_regs:
            try:
                lo_div = _parse_int(lodiv_buf_current_tx)
                if is_ask:
                    # index 0 = off, index 1 = on
                    self._set_frend0(pa_power=1, lodiv_buf_current_tx=lo_div)
                    self._write_patable_index(0, 0x00)
                    self._write_patable_index(1, code & 0xFF)
                else:
                    # FSK/etc: use index 0 directly
                    self._set_frend0(pa_power=0, lodiv_buf_current_tx=lo_div)
                    self._write_patable_index(0, code & 0xFF)
                logger.info(f"Smart power applied: band={band} target={t_dbm}dBm patable=0x{code:02X}")
                return
            except Exception as e:
                logger.warning(f"Smart power regs path failed ({e}); falling back to setPower")

        # Fallback: setPower expects a PATABLE code (exact semantics vary by firmware).
        if hasattr(self.d, "setPower"):
            self.d.setPower(int(code))
            logger.info(f"Smart power applied via setPower: band={band} target={t_dbm}dBm code=0x{code:02X}")
        elif hasattr(self.d, "setTxPower"):
            self.d.setTxPower(int(code))
            logger.info(f"Smart power applied via setTxPower: band={band} target={t_dbm}dBm code=0x{code:02X}")
        else:
            logger.warning("Smart power requested but no setPower/setTxPower available; falling back to max power")
            if hasattr(self.d, "setMaxPower"):
                self.d.setMaxPower()

    def _apply_power_settings(
        self,
        freq_hz: int,
        modulation: str,
        tx_power_mode: str,
        tx_power_target_dbm: Any,
        tx_power_band: Any,
        frend0_pa_power: Any,
        frend0_lodiv_buf_current_tx: Any,
        patable: Any,
    ) -> None:
        mode = (tx_power_mode or "smart").strip().lower()

        if mode in ("max", "maximum", "full"):
            if hasattr(self.d, "setMaxPower"):
                self.d.setMaxPower()
            return

        if mode in ("default", "auto", "keep", "none"):
            return

        if mode in ("smart", "preset", "table"):
            self._apply_smart_power(
                freq_hz=freq_hz,
                modulation=modulation,
                target_dbm=tx_power_target_dbm,
                band_override=tx_power_band,
                lodiv_buf_current_tx=frend0_lodiv_buf_current_tx,
            )
            return

        if mode in ("manual", "register", "frend0"):
            self._apply_manual_regs(
                modulation=modulation,
                frend0_pa_power=frend0_pa_power,
                frend0_lodiv_buf_current_tx=frend0_lodiv_buf_current_tx,
                patable=patable,
            )
            return

        raise ValueError(f"Unknown tx_power_mode: {tx_power_mode}")

    # ---------------------------------------------------------------------
    # Public TX API
    # ---------------------------------------------------------------------

    def transmit(
        self,
        freq: int,
        payload: bytes,
        repeat: int = 20,
        drate: int = 3333,
        modulation: str = "ASK_OOK",
        manchester: bool = False,
        deviation: Optional[int] = None,
        syncmode: int = 0,
        preamble: int = 0,
        # Back-compat for tests/old callers
        max_power: bool = False,
        # New power config
        tx_power_mode: str = "max",
        tx_power_target_dbm: Any = 0,
        tx_power_band: Any = "auto",
        frend0_pa_power: Any = None,
        frend0_lodiv_buf_current_tx: Any = None,
        patable: Any = None,
    ) -> None:
        if rflib is None:
            raise ImportError("rflib is not available (RfCat not installed)")

        try:
            self.d.setFreq(int(freq))

            mod = str(modulation).upper()
            if mod in ("ASK_OOK", "OOK", "ASK"):
                mdm = rflib.MOD_ASK_OOK
            elif mod in ("2FSK", "FSK"):
                mdm = rflib.MOD_2FSK
            else:
                raise ValueError(f"Unknown modulation: {modulation}")

            if manchester and hasattr(rflib, "MANCHESTER"):
                mdm |= rflib.MANCHESTER

            self.d.setMdmModulation(mdm)
            self.d.setMdmDRate(int(drate))
            self.d.setMdmSyncMode(int(syncmode))
            self.d.setMdmNumPreamble(int(preamble))

            if hasattr(self.d, "setMdmManchester"):
                self.d.setMdmManchester(1 if manchester else 0)

            if deviation is not None and mod in ("2FSK", "FSK"):
                self.d.setMdmDeviatn(int(deviation))

            # Apply power AFTER modem config and AFTER setFreq (band matters)
            if max_power:
                tx_power_mode = "max"
            self._apply_power_settings(
                freq_hz=int(freq),
                modulation=mod,
                tx_power_mode=tx_power_mode,
                tx_power_target_dbm=tx_power_target_dbm,
                tx_power_band=tx_power_band,
                frend0_pa_power=frend0_pa_power,
                frend0_lodiv_buf_current_tx=frend0_lodiv_buf_current_tx,
                patable=patable,
            )

            self.d.makePktFLEN(len(payload))
            logger.info(f"TX {len(payload)} bytes @ {freq}Hz")
            self.d.RFxmit(bytes(payload), repeat=int(repeat))

        except Exception as e:
            logger.error(f"Transmission failed: {e}")
            raise
        finally:
            try:
                self.d.setModeIDLE()
            except Exception:
                pass
