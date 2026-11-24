# Evidence AI-4.0 (G1)

Tests chạy với Python 3.12.3 và SciPy 1.18.1, EV2Gym 2.0.0 trên Ubuntu 24.04/WSL2. Checkout tạm pin local base `d2b5d4869bff35ad9e417bee504c6dbf652258b1` và áp [candidate patch](raw/candidate.patch). SHA-256 của candidate là `986fd42e0d00e57e8bbad2a085bba1df9508e2b2b34786e967d7105062644873`. Manifest benchmark lấy HEAD của checkout pin. Patch hash xác định chính xác phần code/test mới đã chạy. [Môi trường](raw/environment.stdout.txt) · [Exit codes](raw/exit-codes.tsv) · [Checksums](CHECKSUMS.sha256)

- `regression-before.patch` là patch chỉ thêm sáu test vào code base. `regression-before.*.txt` chứng minh fail trước sửa. `candidate-initial.patch` là bản trung gian qua 90 focused tests. `candidate.patch` là bản đầy đủ dùng cho final gate.
- `golden-crlf-candidate.tar.gz` giữ output candidate. Reference dùng archive audit từ P0 (historical `70d0eaf`, CRLF). Module map và comparator nguyên bản.
- `backend-benchmark/` giữ report, manifest, seeds, policy, resolved experiments và fingerprints. `benchmark-provenance.stdout.txt` so đầy đủ với frozen baseline. `postgres-ddl-offline.stdout.txt` là DDL migration được render cho PostgreSQL, trạng thái runtime PostgreSQL vẫn pending.

## Tái lập

Chạy từ gốc P-019. Cần clone mirror cùng cấp `../P-019-chatgpt`, venv `.simulator` (có thể override bằng `P0_VENV`) và môi trường hỗ trợ Unix socketpair để solver thread đánh thức asyncio loop. Harness dùng checkout và SQLite riêng. Đặt output mới để giữ evidence cũ.

```bash
scratch=$(mktemp -d /tmp/chargepilot-g1-repro.XXXXXX)
G1_EVIDENCE_OUT="$scratch/evidence" \
  bash eval/evidence/2026-11-24-ai4-4-0/run_gate.sh "$scratch"
```

Reproduce fail-before bằng cách áp `raw/regression-before.patch` lên checkout `d2b5d48`, rồi chạy lệnh ở đầu `raw/regression-before.stdout.txt`. Xem từng mã thoát trong `exit-codes.tsv`. So checksum của evidence bàn giao bằng `sha256sum -c CHECKSUMS.sha256` từ thư mục này.
