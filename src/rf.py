import logging
from typing import Optional


logger = logging.getLogger("RFDriver")


try:
    import rflib  # type: ignore
except Exception:  # pragma: no cover
    rflib = None


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
    ) -> None:
        if rflib is None:
            raise ImportError("rflib is not available (RfCat not installed)")

        if isinstance(payload, str):
            raise TypeError("payload must be bytes, not str")
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(f"payload must be bytes-like, got {type(payload)}")

        try:
            self.d.setFreq(int(freq))

            mod = str(modulation).upper().strip()
            mod_map = {
                "2FSK": rflib.MOD_2FSK,
                "GFSK": rflib.MOD_GFSK,
                "ASK_OOK": rflib.MOD_ASK_OOK,
                "MSK": rflib.MOD_MSK,
            }
            if mod not in mod_map:
                raise ValueError(f"Unsupported modulation: {mod}")

            mod_val = mod_map[mod]
            if manchester:
                # rflib exposes this constant; it's OR'ed into the mod.
                mod_val = mod_val | getattr(rflib, "MANCHESTER", 0x08)

            self.d.setMdmModulation(mod_val)
            self.d.setMdmDRate(int(drate))

            # Only meaningful for (G)FSK
            if deviation is not None and mod in ("2FSK", "GFSK"):
                self.d.setMdmDeviatn(int(deviation))

            self.d.setMdmSyncMode(int(syncmode))
            self.d.setMdmNumPreamble(int(preamble))
            if max_power:
                self.d.setMaxPower()

            self.d.makePktFLEN(len(payload))
            logger.info(f"TX {len(payload)} bytes @ {freq}Hz")
            self.d.RFxmit(bytes(payload), repeat=int(repeat))
        except Exception as e:
            logger.error(f"Transmission failed: {e}")
            raise
        finally:
            # Try to reset idle state
            try:
                self.d.setModeIDLE()
            except Exception:
                pass
