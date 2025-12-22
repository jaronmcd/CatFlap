import logging
from typing import Optional, Any

logger = logging.getLogger("RFDriver")

try:
    import rflib  # type: ignore
except Exception:  # pragma: no cover
    rflib = None


def _parse_tx_power(value: Any) -> tuple[Optional[int], bool]:
    """
    Returns (raw_power, use_max).

    Accepted values:
      - None / "" / "max" / "maximum" => (None, True)
      - "default" / "auto"            => (None, False)  # don't touch power
      - int or numeric string (dec/hex like "0x08") => (int_value, False)
    """
    if value is None:
        return None, True

    if isinstance(value, bool):
        # If someone passes True/False accidentally, treat True as max, False as default.
        return (None, True) if value else (None, False)

    if isinstance(value, int):
        return value, False

    s = str(value).strip().lower()
    if s == "":
        return None, True
    if s in ("max", "maximum", "full"):
        return None, True
    if s in ("default", "auto", "keep"):
        return None, False

    # Accept "8", "08", "0x08"
    return int(s, 0), False


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
        max_power: bool = True,
        tx_power: Any = None,  # "max" | "default" | int | "0x.."
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


            # Power control:
            # - If tx_power is explicitly provided, it overrides max_power behavior.
            if tx_power is not None:
                raw, use_max = _parse_tx_power(tx_power)
                if raw is not None:
                    # Prefer setPower if present; fall back if firmware differs.
                    if hasattr(self.d, "setPower"):
                        self.d.setPower(int(raw))
                    elif hasattr(self.d, "setTxPower"):
                        self.d.setTxPower(int(raw))
                    else:
                        logger.warning("tx_power requested but no setPower/setTxPower available; ignoring")
                elif use_max:
                    if hasattr(self.d, "setMaxPower"):
                        self.d.setMaxPower()
                else:
                    # "default"/"auto": don't touch power
                    pass
            else:
                # Back-compat: payload-controlled max_power
                if max_power and hasattr(self.d, "setMaxPower"):
                    self.d.setMaxPower()

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
