# Log thô của refactor Unified Core

`phase0/`, `phase1/`, `phase2/` chứa log và manifest của từng phase.

Công cụ so sánh đã chuyển sang `scripts/refactor/` (có negative test ở `tests/test_refactor_tools.py`):

| Công cụ | Trước đây | Việc |
|---|---|---|
| `scripts/refactor/ast_manifest.py` | `phase0/astmanifest.py` | in hash AST từng hàm / lớp / hằng số cấp module |
| `scripts/refactor/compare_ast_manifest.py` | `phase1/compare_manifest.py` | cổng "chỉ di chuyển": exit 1 khi định nghĩa đổi / mất |
| `scripts/refactor/compare_sim_output.py` | `phase0/cmpbench.py` | cổng KPI: exit 1 khi lệch ngoài trường thời gian / metadata được khai báo |

Manifest Phase 0/1 (`*/code_hash_manifest.txt`) sinh bằng bản cũ (chỉ hàm / lớp). Từ Phase 2 manifest có thêm hằng số
cấp module (`phase2/baseline_manifest.txt`, 345 định nghĩa).
