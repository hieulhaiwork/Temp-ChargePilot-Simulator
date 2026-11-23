"""Station core dùng chung cho simulator standalone và backend (ADR-019 Phase 4, quyết định 7).

    kernel.py          StationKernel: observe / boundary / propose / approve / apply_approved / advance
    algorithms.py      ghép dispatch / optimizer / coordinator (registry của src/optimizer) + DC model (planning)
    queue.py           phiên sạc, hàng chờ theo vùng, mốc sự kiện xe đến / rời / rút DC (event)
    ev2gym_adapter.py  tích phân năng lượng qua EV2Gym (physics)
    charging_models/   mô hình nhận công suất DC (physics)

Chỉ dùng stdlib, numpy / scipy / ev2gym, hợp đồng `src.models` (stdlib), thuật toán `src.optimizer` và Physical Guard
`src.guard.physical.validator`. Không import stack backend.
"""
