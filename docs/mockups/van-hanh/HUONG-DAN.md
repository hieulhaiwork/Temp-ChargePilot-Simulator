# ChargePilot – Giao diện vận hành trạm

## Mở và sử dụng bộ tệp

- **Mở bản tương tác.** Mở `van-hanh/operator.html` trong Chrome, Edge, Firefox hoặc Safari (màn rộng từ 1.280 px). Dùng các tab trên header để chuyển màn.
- **Xem mọi tình huống.** Bấm “Kịch bản mẫu” trên header, chọn màn và tình huống rồi bấm “Xem tình huống”. Có thể mở thẳng bằng địa chỉ, ví dụ `operator.html#/approvals?state=blocked`.
- **Dùng chung template với cư dân.** Token màu, phông Be Vietnam Pro và component (`.btn`, `.panel`, `.tag`, `.notice`, `.field`, hộp thoại) lấy từ `../cu-dan/assets/ui.css`. Bộ icon và helper ở `../cu-dan/assets/kit.js`. File `assets/van-hanh.css` chỉ thêm khung header-tab (theo `RoleShell` vận hành của nhánh `buivanlam`) và các khối riêng: KPI, lưới đầu nối, Gantt, bảng.
- **Bố cục theo nhánh `buivanlam`.** Bốn màn S5–S8 giữ bố cục của bản TSX trên nhánh đó, bổ sung đủ trạng thái lỗi, rỗng, mất kết nối, 501 theo spec 21 §3.

Bản HTML chạy cục bộ, không gọi máy chủ. Mọi số là minh hoạ. Tên luật Guard, nguồn lệnh, loại đề nghị, chiến lược và chỉ số khớp `src/models/control.py`, `src/models/charging.py` và `src/models/simulation.py`.

## Đăng nhập (chung hai vai trò)

Mở `../login.html`. Tài khoản mẫu `cu.dan@demo.vn` chuyển sang cổng cư dân, `van.hanh@demo.vn` chuyển sang bộ này.

**9 tình huống:** Chưa nhập · Đã nhập đủ · Đang đăng nhập · Sai email hoặc mật khẩu (401) · Email không hợp lệ (422) · Phiên đã hết hạn · Sau khi xoá tài khoản · Máy chủ đang khởi động · Dịch vụ chưa sẵn sàng (501)

## Năm màn hình

### S5 · Dashboard trạm — `operator.html`

Bốn KPI trên một hàng (tải trạm so với giới hạn, đầu nối, hàng chờ, Optimizer + Guard). Bên trái là lưới 8 đầu nối A01–A08 và biểu đồ tải 24 giờ có vạch giới hạn. Bên phải là đề nghị cần duyệt và sự kiện gần nhất.

- Trạng thái đầu nối luôn ghi bằng chữ và icon, không chỉ dùng màu. Ô có viền vàng là xe có nguy cơ trễ hạn.
- Bấm một ô để mở chi tiết: xe (mã giả danh), pin, hạn, lịch công suất, 5 quyết định gần nhất. Màn này chỉ xem, không gửi lệnh trực tiếp.
- “Tạm dừng” đóng băng phần hiển thị, dữ liệu mới vẫn được nhận.

**13 tình huống:** Trực tiếp · Nguồn giảm còn 20 kW (AC5) · Guard vừa chặn một lệnh (AC6) · Chi tiết đầu nối A07 · Biểu đồ đang xem một mốc giờ · Xem tất cả sự kiện · Tạm dừng cập nhật · Dữ liệu cũ hơn 60 giây · Mất kết nối trực tiếp · Đang tải · Trạm vừa khởi động · Một khối lỗi · Dịch vụ chưa sẵn sàng (501)

### S9 · Sơ đồ bãi — `operator-map.html`

Mặt bằng bãi hybrid AC/DC theo ADR-010 (Proposed): 2 tủ AC × 11 kW, 1 tủ DC 2 × 60 kW, lưới 106 kW. Bộ vẽ SVG `../cu-dan/assets/site-map.js` dùng chung với màn sơ đồ của cư dân.

- Bốn KPI theo tầng: đầu vào lưới, ngân sách AC, ngân sách DC, cổng và hàng chờ.
- Chọn ô bằng chuột hoặc phím mũi tên và Enter. Lọc theo vùng AC/DC. Có bảng số liệu tương đương.
- Lưu ý: S5–S8 vẫn dùng 8 đầu nối A01–A08 của PRD v0.2 cho tới khi ADR-010 được duyệt.

**7 tình huống:** Cao điểm tối · Luân chuyển cổng · Cổng DC-01-2 báo lỗi · Mất kết nối trực tiếp · Đang tải · Lỗi tải sơ đồ · Dịch vụ chưa sẵn sàng (501)

### S6 · Hàng đợi & lịch — `operator-schedule.html`

Gantt theo đầu nối từ 17:00 tới 07:00 hôm sau, có vạch “bây giờ”, vùng cao điểm và thấp điểm. Khối giảm công suất có vân sọc để không chỉ dựa vào màu. Bên phải là hàng đợi xe chờ với “Xếp thủ công”.

- Thử xếp `#31ab07`: chọn A03 thì đã xếp, A06 thì chờ duyệt, A01 hoặc A05 thì Guard chặn.
- Đổi ngày sang 16/11 để xem chế độ chỉ xem, sang ngày khác để xem trạng thái không có lịch.

**16 tình huống:** Lịch hôm nay · Đang lập lịch lại · Đã lập lịch lại · Xếp thủ công đang gửi · Đã xếp · Chờ duyệt · Guard chặn (AC6) · Hàng chờ thiếu chi tiết · Ngày khác chỉ xem · Không có lịch cho ngày · Lịch chưa có phiên · Không có xe chờ · Mất kết nối trực tiếp · Đang tải · Lỗi tải · Dịch vụ chưa sẵn sàng (501)

### S7 · Duyệt lệnh — `operator-approvals.html`

Ba tab: Chờ duyệt, Bị Guard chặn, Nhật ký quyết định. Bên trái là danh sách, bên phải là chi tiết dòng đang chọn.

- Đề nghị loại “Cư dân đồng ý” chỉ theo dõi, vận hành không có nút quyết định. Đồng hồ đếm ngược đổi màu dưới 5 phút.
- Tab Bị Guard chặn hiện luật, mã lệnh, phiên bản lịch, thời điểm trạng thái, người ra lệnh, giờ Guard kiểm (AC6, US7).
- Nhật ký lọc theo kết quả: ai đề xuất, Guard kết luận gì, ai duyệt, có thực thi không (FR14).

**14 tình huống:** Chờ duyệt · Đang gửi quyết định · Đã duyệt · Đã duyệt nhưng Guard chặn khi thực thi · Đề nghị đã được xử lý trước đó (409) · Một đề nghị hết hạn · Tab Bị Guard chặn · Tab Nhật ký quyết định · Mất kết nối trực tiếp · Không có đề nghị · Đang tải · Lỗi tải · Dịch vụ chưa sẵn sàng (501) · Chưa gửi được quyết định (501)

### S8 · Mô phỏng kịch bản — `operator-simulation.html`

Chạy kịch bản trong `config/scenarios/` với chiến lược A–D, bơm sự cố vào trạm mô phỏng và so bảng đối chứng MT1–MT6.

- Đặt số xe bằng 0 để thấy lỗi tại ô. Chọn “Nguồn giảm” để thấy kịch bản chưa có đối chứng.
- “Bơm sự cố” luôn hỏi xác nhận, nút an toàn “Không bơm” nhận focus trước.

**12 tình huống:** Có bảng đối chứng · Đang chạy · Chạy xong thêm cột · Dữ liệu cần sửa · Kịch bản chưa có đối chứng · Sự cố đổi giới hạn nguồn · Xác nhận bơm sự cố · Đã bơm sự cố · Đang tải · Chưa có kịch bản · Lỗi tải · Dịch vụ chưa sẵn sàng (501)
