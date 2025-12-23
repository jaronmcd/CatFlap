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
    # XDATA access (peek/poke)
    # ---------------------------------------------------------------------

    def _xdata_read(self, addr: int, size: int = 1) -> Optional[bytes]:
        if hasattr(self.d, "peek"):
            try:
                b = self.d.peek(addr, size)
                return bytes(b)
            except Exception:
                return None
        return None

    def _xdata_write(self, addr: int, data: bytes) -> bool:
        if hasattr(self.d, "poke"):
            try:
                self.d.poke(addr, data)
                return True
            except TypeError:
                # Some builds accept list[int]
                try:
                    self.d.poke(addr, list(data))
                    return True
                except Exception:
                    return False
            except Exception:
                return False
        return False

    def _write_patable_index(self, index: int, value: int) -> None:
        if index < 0 or index > 7:
            raise ValueError("PATABLE index must be 0..7")
        addr = PA_TABLE0_ADDR - index
        ok = self._xdata_write(addr, bytes([value & 0xFF]))
        if not ok:
            raise RuntimeError("Unable to write PATABLE (poke() not available or failed)")

    def _apply_power_settings(
        self,
        modulation: str,
        tx_power_mode: str = "max",
        frend0_pa_power: Any = None,
        frend0_lodiv_buf_current_tx: Any = None,
        patable: Any = None,
    ) -> None:
        """Apply CC1110/CC1111 transmit power configuration.

        tx_power_mode:
          - "max"     -> call rflib setMaxPower() (recommended default)
          - "default" -> don't touch any power registers
          - "manual"  -> program FREND0 + PATABLE using XDATA peek/poke

        FREND0 bitfields (0xDF1B):
          - LODIV_BUF_CURRENT_TX (bits 5:4): TX LO buffer current (0..3)
          - PA_POWER             (bits 2:0): PATABLE index used for TX (0..7)

        PATABLE (PA_TABLE0..PA_TABLE7):
          - Single value: "0xC0" -> treated as the ON level (index 0 forced to 0x00 for ASK/OOK)
          - List/CSV of up to 8 values -> writes PA_TABLE0..PA_TABLE7 explicitly
        """
        mode = (tx_power_mode or "max").strip().lower()

        if mode in ("max", "maximum", "full"):
            if hasattr(self.d, "setMaxPower"):
                self.d.setMaxPower()
            return

        if mode in ("default", "auto", "keep", "none"):
            return

        if mode not in ("manual", "register", "frend0"):
            raise ValueError(f"Unknown tx_power_mode: {tx_power_mode}")

        pa_power = _parse_int(frend0_pa_power)
        lo_div = _parse_int(frend0_lodiv_buf_current_tx)
        pt = _parse_patable(patable)

        # Sensible default for ASK/OOK: PA_POWER=1 (index 0 = '0', index 1 = '1')
        if pa_power is None:
            pa_power = 1

        if not (0 <= pa_power <= 7):
            raise ValueError("frend0_pa_power must be 0..7")
        if lo_div is not None and not (0 <= lo_div <= 3):
            raise ValueError("frend0_lodiv_buf_current_tx must be 0..3")

        cur = self._xdata_read(FREND0_ADDR, 1)
        if cur is None:
            raise RuntimeError("Manual power mode requires firmware with peek()/poke() support")

        cur_val = cur[0]
        new_val = cur_val

        # Bits 5:4 -> LODIV_BUF_CURRENT_TX
        if lo_div is not None:
            new_val = (new_val & ~(0b11 << 4)) | ((lo_div & 0b11) << 4)

        # Bits 2:0 -> PA_POWER
        new_val = (new_val & ~0b111) | (pa_power & 0b111)

        if new_val != cur_val:
            if not self._xdata_write(FREND0_ADDR, bytes([new_val])):
                raise RuntimeError("Unable to write FREND0 (poke() failed)")

        if pt is None:
            logger.warning("Manual power mode selected but 'patable' not provided; leaving PATABLE unchanged")
            return

        is_ask = str(modulation).upper() in ("ASK_OOK", "ASK", "OOK") or str(modulation).upper().startswith("ASK")

        # Single value -> treat as ON level; fill indices up to PA_POWER
        if len(pt) == 1:
            on_val = pt[0] & 0xFF

            if is_ask:
                # In ASK/OOK, index 0 is used for '0' -> make sure it's truly off.
                self._write_patable_index(0, 0x00)

            start = 1 if is_ask else 0
            for idx in range(start, pa_power + 1):
                self._write_patable_index(idx, on_val)
            return

        if len(pt) > 8:
            raise ValueError("patable list may have at most 8 entries (PA_TABLE0..PA_TABLE7)")

        for idx, v in enumerate(pt):
            self._write_patable_index(idx, v & 0xFF)

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
        # New power configuration
        tx_power_mode: str = "max",
        frend0_pa_power: Any = None,
        frend0_lodiv_buf_current_tx: Any = None,
        patable: Any = None,
    ) -> None:
        if rflib is None:
            raise ImportError("rflib is not available (RfCat not installed)")

        try:
            self.d.setFreq(int(freq))

            # Modulation selection
            mod = str(modulation).upper()
            if mod in ("ASK_OOK", "OOK", "ASK"):
                mdm = rflib.MOD_ASK_OOK
            elif mod in ("2FSK", "FSK"):
                mdm = rflib.MOD_2FSK
            else:
                raise ValueError(f"Unknown modulation: {modulation}")

            # Manchester: older rflib expects this bit OR'ed into modulation.
            if manchester and hasattr(rflib, "MANCHESTER"):
                mdm |= rflib.MANCHESTER

            self.d.setMdmModulation(mdm)

            self.d.setMdmDRate(int(drate))
            self.d.setMdmSyncMode(int(syncmode))
            self.d.setMdmNumPreamble(int(preamble))

            # Also call setMdmManchester when available (some firmwares expose it)
            if hasattr(self.d, "setMdmManchester"):
                self.d.setMdmManchester(1 if manchester else 0)

            if deviation is not None and mod in ("2FSK", "FSK"):
                self.d.setMdmDeviatn(int(deviation))

            # Apply power settings AFTER modem configuration
            self._apply_power_settings(
                modulation=mod,
                tx_power_mode=tx_power_mode,
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
