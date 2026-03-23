from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if "appdaemon.plugins.hass.hassapi" not in sys.modules:
    appdaemon = types.ModuleType("appdaemon")
    plugins = types.ModuleType("appdaemon.plugins")
    hass = types.ModuleType("appdaemon.plugins.hass")
    hassapi = types.ModuleType("appdaemon.plugins.hass.hassapi")

    class FakeHass:
        pass

    hassapi.Hass = FakeHass
    appdaemon.plugins = plugins
    plugins.hass = hass
    hass.hassapi = hassapi

    sys.modules["appdaemon"] = appdaemon
    sys.modules["appdaemon.plugins"] = plugins
    sys.modules["appdaemon.plugins.hass"] = hass
    sys.modules["appdaemon.plugins.hass.hassapi"] = hassapi
