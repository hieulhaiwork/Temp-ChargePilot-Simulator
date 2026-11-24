# Evidence P0 — ChargePilot AI-4

Code chạy tại `ce23136d50ad08abb7c9fdc98eff791875d24516`. Raw có cwd, lệnh, stdout/stderr, mã thoát và mốc UTC. [Exit codes](raw/exit-codes.tsv) · [SHA-256](CHECKSUMS.sha256)

- `raw/local-tree.stdout.txt`, `mirror-tree.stdout.txt`, `mirror-tree-diff.stdout.txt` và `github-commit.json` ghi mapping baseline. Diff exit 1 là 12 path metadata chỉ có ở repo chính.
- `raw/golden-outputs.tar.gz` giữ output LF, `raw/golden-crlf-outputs.tar.gz` giữ output CRLF. Mỗi archive gồm sáu nhóm workload cho cả candidate và historical reference. Reference chạy `70d0eaf4f326b9a9317258bec44d7d71bbe60ffe` với nguyên gate driver HEAD. `golden-scenario-hashes` chứng minh fixture JSON giống nhau về dữ liệu và hash CRLF trùng evidence 2026-11-22.
- `raw/backend-benchmark/` giữ manifest, benchmark JSON và bảng MD của 100 run. Manifest và từng run chứa resolved experiment. `benchmark-provenance.stdout.txt` giữ fingerprint và phân bố timing riêng. Comparator của repo giữ nguyên.
- `raw/issue-probe-final.*.txt` là kết quả R01–R05. Probe đầu trong sandbox bị treo khi event loop chờ solver. Lần retry đầu ngoài sandbox có assertion của probe đặt sai độ dài cả trace là 1 phút. Trace thực tế dài 2 phút và simulator dừng ngay ở bước vi phạm. Probe cuối kiểm khoảng đo dương cho trace chứa vi phạm và kiểm riêng ca 0 phút. Product code vẫn tại cùng commit.
- `raw/environment.stdout.txt` ghi OS, CPU, phiên bản Python và gói. `raw/config-hashes.stdout.txt` ghi SHA-256 của input và frozen evidence. Các test dùng fixture tổng hợp, SQLite tạm và không nạp `.env` workspace.

## Tái lập

Chạy từ gốc P-019. `MIRROR_CLONE` mặc định là `../P-019-chatgpt` và `P0_VENV` mặc định là `.simulator`. Harness ghi output ra thư mục tạm được in khi khởi động. Backend pytest và benchmark cần runtime cho phép gửi dữ liệu qua Unix socketpair, để solver thread đánh thức asyncio loop.

```bash
P0_BASELINE_HEAD=ce23136d50ad08abb7c9fdc98eff791875d24516 P0_SKIP_ASYNC=1 \
  bash eval/evidence/2026-11-24-ai4-p0/run.sh
# Thay <scratch> bằng thư mục cha của evidence/ vừa in.
bash eval/evidence/2026-11-24-ai4-p0/run_golden_crlf.sh <scratch>
bash eval/evidence/2026-11-24-ai4-p0/run_async_checks.sh <scratch>
```

Đọc exit code từng gate trong `<scratch>/evidence/exit-codes.tsv`. Hành vi fail LF được giữ nguyên trong so sánh. Kiểm tra archive evidence lưu trong repo bằng `sha256sum -c CHECKSUMS.sha256` từ thư mục này.
