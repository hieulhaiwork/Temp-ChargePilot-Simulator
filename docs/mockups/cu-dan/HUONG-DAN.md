# ChargePilot – Giao diện sạc dành cho cư dân

## Mở và sử dụng bộ tệp

- **Đăng nhập và vận hành.** Màn đăng nhập chung ở `../login.html`, bộ vận hành ở `../van-hanh/` (cùng template, xem `../van-hanh/HUONG-DAN.md`).

- **Mở bản tương tác.** Giải nén bộ thiết kế, mở HTML/resident.html trong Chrome, Edge, Firefox hoặc Safari. Dùng thanh điều hướng để chuyển màn. Điện thoại có thanh điều hướng dưới.
- **Xem mọi tình huống.** Mở “Kịch bản mẫu”, chọn màn, chọn tình huống và nhấn “Xem tình huống”. Mỗi lựa chọn nạp một bộ dữ liệu mới, nên hãy hoàn tất luồng đang thử trước khi đổi tình huống.
- **Đưa vào Figma.** Trong Figma Design, tạo một file, kéo các SVG từ Figma/Mobile hoặc Figma/Desktop lên canvas. Hai bộ rộng 390 px và 1.440 px, mỗi bộ có đủ sáu màn, bao gồm phần nội dung phải cuộn.
- **Sửa chữ và bố cục.** Để dựng khung với lớp chữ Figma riêng, cài ba phông trong Figma/Fonts. Trong Figma Desktop tạo một development plugin “Run once”, thay nội dung code.js do Figma tạo bằng Figma/Khoi-tao-layer/code.js, rồi chạy plugin trong file thiết kế của bạn.

Bản HTML chạy cục bộ. Dữ liệu và phản hồi của Trợ lý được mô phỏng. Mỗi lần chọn kịch bản sẽ đặt lại dữ liệu trải nghiệm. Hồ sơ và lịch được lưu trong trình duyệt nếu thiết bị cho phép.

## Bảy màn hình

### 1. Trang chủ

Đưa giờ đạt mức pin mục tiêu lên đầu. Cư dân nhìn được kết quả dự kiến ngay khi mở ứng dụng.

Mở HTML/resident.html. Xem bản thiết kế Figma/Mobile/01-Trang-chu.svg hoặc bản tương ứng trong Figma/Desktop.

- **Lịch sạc đêm nay.** Thẻ chính hiển thị pin hiện tại, mục tiêu, giờ dự kiến đạt mục tiêu và khoảng dự phòng. Với lịch mẫu, xe đạt 80% lúc 05:30, sớm hơn giờ lấy xe 07:00 đúng 1 giờ 30 phút.
- **Các mốc và hàng chờ.** Bốn mốc đi từ cắm xe đến lấy xe. Khi đang chờ, màn hình hiển thị vị trí và giờ bắt đầu dự kiến. Khi trạm gửi đề nghị điều chỉnh, cư dân có thể mở thẳng phần so sánh.
- **Trợ lý sạc.** Có thể chọn một câu gợi ý hoặc tự nhập nhu cầu. Trợ lý giải thích khung giờ, đưa phương án để xác nhận hoặc dẫn sang biểu mẫu khi chưa xử lý được.

**Thử trên bản mẫu.** Chọn “Chưa có lịch sạc”, nhấn gợi ý “80% trước 07:00”, rồi mở phương án từ cuộc trò chuyện. Lịch chỉ được giữ chỗ khi bạn xác nhận.

**13 tình huống trong màn này**

- Đã xác nhận · chờ đến lượt
- Trạm vừa đổi khung sạc
- Trợ lý có phương án chờ xác nhận
- Trợ lý đang trả lời
- Yêu cầu vượt công suất
- Trợ lý tạm ngừng
- Cuộc trò chuyện mới
- Chưa có lịch sạc
- Đang tải
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng
- Mất kết nối trực tiếp
- Tin nhắn quá 5.000 ký tự

### 2. Đặt lịch sạc

Biểu mẫu gom mức pin, thông tin xe và hai mốc giờ vào một lần nhập.

Mở HTML/resident-book.html. Xem bản thiết kế Figma/Mobile/02-Dat-lich.svg hoặc bản tương ứng trong Figma/Desktop.

- **Xe và mức pin.** Chọn mẫu xe rồi nhập pin hiện tại và pin mong muốn. Xe mặc định và mức pin thường dùng lấy từ hồ sơ. Mục tiêu phải cao hơn pin hiện tại và tối đa 100%.
- **Thời gian ở trạm.** “Đặt trước” cho phép chọn giờ cắm và giờ cần lấy xe. “Đến trực tiếp” lấy giờ đến của phiên mô phỏng. Giờ lấy phải sau giờ cắm. Lỗi xuất hiện cạnh ô cần sửa.
- **Ước tính trước khi đặt.** Điện vào pin, điện lấy từ lưới và chi phí thay đổi theo dữ liệu nhập. Nút “Xem phương án” chuyển sang bước xem xét. Nếu đã có lịch hiệu lực, có lối tắt tới lịch đang giữ.

**Thử trên bản mẫu.** Trong “Kịch bản mẫu”, chọn Đặt lịch và “Điền sẵn từ hồ sơ”. Giữ xe 60 kWh, pin 32% lên 80%, cắm 23:00 và lấy 07:00 hôm sau. Nhấn “Xem phương án”.

**9 tình huống trong màn này**

- Điền sẵn từ hồ sơ
- Xe đã có lịch hiệu lực
- Đến trực tiếp
- Dữ liệu cần sửa
- Đang gửi
- Đang tải
- Danh mục xe trống
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng

### 3. Phương án và lịch sạc

Dùng cùng một màn để duyệt phương án trước khi đặt và quản lý lịch sau khi xác nhận.

Mở HTML/resident-plan.html. Xem bản thiết kế Figma/Mobile/03-Phuong-an-sac.svg hoặc bản tương ứng trong Figma/Desktop.

- **Xem khung sạc.** So sánh giờ cắm, giờ bắt đầu, giờ đạt mục tiêu và giờ lấy xe. Dải thời gian có chú giải khung sạc và giờ thấp điểm. Phần chi tiết tách điện vào pin, điện từ lưới và chi phí.
- **Khi phương án chưa kịp.** Trạng thái hàng chờ cho thấy xe ở vị trí 3, hoàn tất 07:40, muộn 40 phút. Chọn giảm pin mục tiêu hoặc dời giờ lấy xe để tính lại và xem kết quả trước khi giữ chỗ.
- **Xác nhận, đổi và huỷ.** Khi phương án kịp và còn hiệu lực, xem phạm vi trạm được điều chỉnh rồi chọn “Xác nhận lịch”. Lịch đã đặt có mã riêng. Có thể đổi mục tiêu, đổi giờ lấy hoặc xác nhận huỷ trong hộp thoại.

**Thử trên bản mẫu.** Chọn Lịch sạc và “Trong hàng chờ · trễ giờ lấy”. Chọn một phương án thay thế, kiểm tra giờ hoàn tất mới, rồi xác nhận. Mở lại lịch để thử đổi hoặc huỷ.

**17 tình huống trong màn này**

- Phương án từ Trợ lý
- Phiên chờ của Trợ lý đã mất
- Trạm thay đổi trước khi xác nhận
- Phương án từ biểu mẫu
- Trong hàng chờ · trễ giờ lấy
- Đang xác nhận
- Đã có lịch khác
- Đã hết hạn
- Lịch đã xác nhận
- Xe đang sạc
- Đổi yêu cầu
- Xác nhận huỷ
- Mất kết nối trực tiếp
- Chưa có phương án
- Đang tải
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng

### 4. Thông báo

Gom cập nhật của trạm vào một hộp thư và đánh dấu rõ những tin cần cư dân quyết định.

Mở HTML/resident-notifications.html. Xem bản thiết kế Figma/Mobile/04-Thong-bao.svg hoặc bản tương ứng trong Figma/Desktop.

- **Đọc nhanh từng tin.** Mỗi tin có loại, giờ nhận, tiêu đề và tóm tắt. Có bốn loại gồm đề nghị cần phản hồi, bảo vệ khẩn cấp, lịch đã đổi và thông tin chung.
- **Lọc và đánh dấu đã đọc.** Ba bộ lọc gồm “Tất cả”, “Chưa đọc” và “Cần phản hồi”. Mở chi tiết một tin sẽ cập nhật trạng thái đã đọc của riêng tin đó và số đếm trên giao diện.
- **Đi tới quyết định.** Từ tin điều chỉnh, “Trả lời đề nghị” mở màn so sánh trước và sau. Sau khi trả lời, cư dân vẫn có thể mở lại đề nghị để xem quyết định đã ghi nhận.

**Thử trên bản mẫu.** Chọn “Hai tin chưa đọc”. Mở “Xem thêm” ở tin bảo vệ khẩn cấp và kiểm tra số chưa đọc giảm còn một. Chọn “Cần phản hồi” để tìm đề nghị của A07.

**8 tình huống trong màn này**

- Hai tin chưa đọc
- Đã mở chi tiết một tin
- Có thông báo mới
- Mất kết nối trực tiếp
- Đang tải
- Hộp thư trống
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng

### 5. Đề nghị điều chỉnh

Đặt tác động tới giờ lấy xe trước thông số kỹ thuật và cạnh quyết định của cư dân.

Mở HTML/resident-approval.html. Xem bản thiết kế Figma/Mobile/05-De-nghi-dieu-chinh.svg hoặc bản tương ứng trong Figma/Desktop.

- **So sánh trước và sau.** Trạm đề nghị giảm A07 từ 7 kW xuống 3,5 kW trong khoảng 23:00 đến 00:00. Giờ đạt 80% đổi từ 05:30 sang 06:10. Xe vẫn kịp giờ lấy 07:00, với 50 phút dự phòng.
- **Phản hồi có thời hạn.** Đồng hồ hiển thị thời gian còn lại, có trạng thái riêng dưới một phút. Cư dân có thể thêm ghi chú tối đa 500 ký tự rồi chọn “Đồng ý” hoặc “Từ chối”.
- **Kết quả và hết hạn.** Quyết định đã gửi có thể xem lại. Đồng ý ghi nhận phản hồi cho trạm kiểm tra điều kiện áp dụng. Từ chối hoặc hết giờ khi chưa trả lời sẽ giữ lịch trước đề nghị.

**Thử trên bản mẫu.** Chọn “Chờ phản hồi”, thêm ghi chú rồi nhấn “Đồng ý”. Mở lại tin để đọc quyết định. Chọn tình huống “Đã hết hạn” để xem kết quả khi cư dân chưa kịp trả lời.

**15 tình huống trong màn này**

- Chờ phản hồi
- Còn dưới một phút
- Đang thêm ghi chú
- Đang gửi
- Đã hết hạn
- Đã đồng ý · chỉ đọc
- Đã từ chối · chỉ đọc
- Phản hồi tới sau khi hết hạn
- Chưa có thời hạn trả lời
- Đủ thông số công suất trước và sau
- Không tìm thấy đề nghị
- Đang tải
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng
- Chưa gửi được quyết định

### 6. Hồ sơ cư dân

Tách thông tin mặc định của xe khỏi quyền cư dân cho phép trạm sử dụng.

Mở HTML/resident-profile.html. Xem bản thiết kế Figma/Mobile/06-Ho-so.svg hoặc bản tương ứng trong Figma/Desktop.

- **Thông tin dùng khi đặt lịch.** Sửa tên hiển thị, xe mặc định và mức pin thường dùng. Các giá trị đã lưu sẽ điền sẵn cho những lần đặt lịch sau. Tóm tắt bên cạnh cho thấy cấu hình hiện hành.
- **Ba quyền của trạm.** Chọn mức lùi giờ bắt đầu tối đa. Có hai công tắc riêng cho giảm công suất khi vẫn kịp hạn và giảm công suất khẩn cấp có thông báo sau.
- **Lưu và quản lý tài khoản.** Nút “Lưu thay đổi” bật khi có chỉnh sửa. Hồ sơ phân biệt đang sửa, đang lưu và đã lưu. Phần tài khoản có đăng xuất và hộp xác nhận xoá dữ liệu mẫu trên trình duyệt.

**Thử trên bản mẫu.** Đổi mức pin thường dùng từ 80% lên 85%, nhấn “Lưu thay đổi”, rồi vào Đặt lịch. Ô pin mong muốn sẽ mang giá trị vừa lưu trong cùng phiên trải nghiệm.

**10 tình huống trong màn này**

- Hồ sơ đã lưu
- Có thay đổi chưa lưu
- Tắt quyền bảo vệ khẩn cấp
- Dữ liệu cần sửa
- Đang lưu
- Đã lưu hồ sơ
- Xác nhận xoá tài khoản
- Đang tải
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng

### 7. Sơ đồ bãi

Chỉ chỗ của xe mình trong bãi và cổng còn trống. Theo phương án bãi hybrid AC/DC (ADR-010, chờ duyệt).

Mở HTML/resident-map.html. Màn mới, chưa có bản Figma SVG.

- **Xe của bạn.** Thẻ đầu tiên cho biết xe đang chờ ở làn nào, đang sạc ở ô nào hoặc đã đầy và cần rời ô trước giờ nào.
- **Riêng tư.** Ô của cư dân khác chỉ hiện “Đang dùng”, “Trống” hoặc “Tạm ngưng”, không lộ xe, mức pin hay giờ rời.
- **Đường đi.** Các bước từ lối vào tới đúng ô hoặc làn chờ. Bộ vẽ SVG `assets/site-map.js` dùng chung với màn sơ đồ của vận hành.

**7 tình huống trong màn này**

- Đang chờ ở làn AC, vị trí 1
- Đang sạc tại ô B-A1
- Đã đầy, nhắc rời ô
- Mất kết nối trực tiếp
- Đang tải
- Lỗi kết nối · có thể thử lại
- Dịch vụ chưa sẵn sàng

## Cách tính trong ví dụ

Xe mẫu 60 kWh, từ 32% đến 80%, cần 28,8 kWh vào pin. Với hiệu suất giả định 90%, điện lấy từ lưới là 32 kWh. Giá mẫu 1.200 đồng/kWh cho ước tính 38.400 đồng.

## Tạo lớp chữ và khung riêng trong Figma Desktop

1. Cài ba phông Be Vietnam Pro trong Figma/Fonts và mở một file Figma Design mới.
2. Trong menu **Plugins → Development → New plugin**, chọn Figma Design và mẫu **Run once**. Lưu dự án plugin vào máy.
3. Chép nội dung Figma/Khoi-tao-layer/code.js vào tệp code.js của dự án vừa tạo. Giữ manifest do Figma cấp.
4. Trong **Plugins → Development**, chạy plugin vừa tạo một lần. Mỗi lần chạy sẽ tạo thêm một bộ 12 khung.

[Hướng dẫn Figma Desktop](https://developers.figma.com/docs/plugins/plugin-quickstart-guide/)

## Mẫu Figma có thể tham khảo thêm

- Xem cách bố trí bước chọn giờ, xác nhận và huỷ chỗ. Trang tác giả có nút Preview in Figma. [ChargeMate · UI Ants](https://uiants.co/product/chargemate-ev-charging-app-ui-kit/)
- Xem cách trình bày tiến độ sạc trên điện thoại. [EV Charging App · Nickelfox Design](https://ui4free.com/mobile-templates/ev-charging-app-figma-mobile-template.htm)
