"""Compatibility alias (ADR-019 Phase 2): this module moved to `src.models.station_protocols`.

`sys.modules` maps the old name to the SAME module object (attribute access and monkeypatching hit the real
implementation). Remove in Phase 6 once no caller uses the old path.
"""

import sys

from src.models import station_protocols as _module

sys.modules[__name__] = _module
