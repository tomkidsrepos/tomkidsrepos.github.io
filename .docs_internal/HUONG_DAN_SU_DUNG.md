# HƯỚNG DẪN SỬ DỤNG HỆ THỐNG APPVN RETRO CHO iOS CỔ
**Dự án**: Kho Ứng Dụng AppVN Cài Đặt Trực Tiếp (Tomkids Repo)  
**Địa chỉ Web**: `https://tomkidsrepo.cloud/app/`

---

## 1. TRẢI NGHIỆM TRÊN IPHONE / IPOD TOUCH (iOS 4 - 10)

1. Mở **Safari** trên thiết bị iPhone/iPod và truy cập:
   👉 **`https://tomkidsrepo.cloud/app/`**
2. **Cài đặt như một Ứng Dụng Native (Add to Home Screen)**:
   - Trên Safari, bấm vào biểu tượng **Chia sẻ** (hình mũi tên).
   - Chọn **"Thêm vào Màn hình chính"** (Add to Home Screen).
   - Biểu tượng **AppVN** sẽ xuất hiện trên màn hình Home của bạn. Khi mở ra, app sẽ chạy **toàn màn hình (full-screen)** độc lập y hệt ứng dụng gốc!
3. **Cài đặt Ứng dụng & Game**:
   - Duyệt ứng dụng theo các tab: *Mới nhất*, *Nổi bật*, *Tải nhiều*.
   - Bấm vào biểu tượng **Mũi tên tải** hoặc bấm trực tiếp vào ứng dụng để mở hộp thoại bóng bẩy (Action Sheet):
     - **Xem chi tiết**: Xem mô tả, tác giả, phiên bản.
     - **Cài đặt**: Kích hoạt cài đặt qua SpringBoard (yêu cầu máy đã cài *AppSync Unified*).
     - **Tải lại**: Cài lại ứng dụng nếu gặp sự cố.
4. **Các chuyên mục giải trí khác**:
   - Vuốt mở **Menu trượt bên trái** (hoặc bấm nút Hamburger):
     - **Sách & Truyện**: Bấm "Mở iBooks" để Safari tự lưu vào app iBooks của máy.
     - **Nhạc chuông**: Nghe thử trực tiếp bằng trình phát nhạc HTML5 và tải file `.m4r`.
     - **Hình nền**: Chạm giữ ảnh 1 giây để lưu vào Cuộn Camera (Camera Roll).
     - **Quay thưởng**: Mini-game vòng quay may mắn kiếm thêm Xu & Ruby mỗi ngày!

---

## 2. CÔNG CỤ QUẢN TRỊ CỤC BỘ TRÊN MÁY TÍNH (`appvn_admin.py`)

Để đưa thêm file IPA / DEB mới lên hệ thống mà không cần chỉnh sửa code hay viết file plist thủ công:

### Cách 1: Sử dụng Giao diện Web Admin Cục bộ (Trực quan nhất)
1. Mở Terminal / PowerShell tại thư mục repo `D:\GitHub\Tomkidsrepos\tomkidsrepos.github.io` (hoặc trong thư mục Google Drive).
2. Chạy lệnh:
   ```bash
   python appvn_admin.py
   ```
3. Trình duyệt sẽ tự động mở trang quản trị: **`http://127.0.0.1:8080`**
4. Copy file `.ipa` hoặc `.deb` của bạn vào thư mục `incoming/`.
5. Trên giao diện web, chọn chuyên mục và bấm: **"⚡ Bắt Đầu Xử Lý Tự Động"**.
   - Script sẽ tự động bóc tách `Info.plist`, uncrush icon PNG, sinh file `manifest.plist` và cập nhật `ota_data.json`.
6. Sau khi xong, bấm nút xanh **"📤 Git Commit & Push"** để đẩy thẳng lên `tomkidsrepo.cloud`.

### Cách 2: Chạy dòng lệnh nhanh (CLI)
```bash
python appvn_admin.py "incoming/FlappyBird.ipa" "Trò Chơi" "https://github.com/.../app.ipa"
```

---

## 3. THÊM APP TRỰC TIẾP TRÊN GITHUB ACTIONS (KHÔNG CẦN BẬT MÁY TÍNH)

1. Truy cập vào GitHub: `https://github.com/tomkidsrepos/tomkidsrepos.github.io/actions`
2. Chọn workflow **"Add OTA App"** ở cột bên trái.
3. Bấm **"Run workflow"**:
   - Dán link tải file `.ipa` / `.deb` (hỗ trợ link trực tiếp hoặc link Google Drive).
   - Chọn Chuyên mục (*Trò Chơi, Mạng Xã Hội, Giải Trí, Công Cụ, Hệ thống, Jailbreak*).
   - Bấm nút xanh **Run workflow**.
4. GitHub Actions sẽ tự động tải file, đưa lên Releases `OTA-Storage`, trích xuất thông tin và cập nhật web tự động 100%!
