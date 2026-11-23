"""Compatibility alias (ADR-019 Phase 2): this module moved to `src.optimizer.zones.rolling_lp`.

`sys.modules` maps the old name to the SAME module object, so attribute access, private helpers and monkeypatching
(e.g. tests patching `linprog`) act on the real implementation. Remove in Phase 6 once no caller uses the old path.
"""

import sys

from src.optimizer.zones import rolling_lp as _module

sys.modules[__name__] = _module
