# Plan 55 — Dựng self-hosted runner CI trên laptop (VirtualBox + Ubuntu)

> Trạng thái: đã chạy thật trên máy đầu tiên (`team-19-LufkyMama`, 17/11/2026). Owner: TV4. Liên quan: [50-devops.md](50-devops.md) §4.
> Mục tiêu: **mỗi thành viên dựng một runner** để CI không phụ thuộc vào một laptop duy nhất.

## 1. Vì sao cần, và nhiều runner hoạt động thế nào

- Org `AI20K-Build-Phase-Cohort-5` không cấp phút GitHub-hosted cho repo private, nên `ci.yml` chạy trên
  `runs-on: [self-hosted, team-19]`.
- Mọi runner mang nhãn `team-19` dùng chung một hàng đợi. GitHub giao job cho **máy nào đang online và rảnh**. Chỉ cần
  một người bật VM là CI chạy; càng nhiều máy bật thì 4 job càng chạy song song.
- Không máy nào bật thì job ở trạng thái **Queued** (vàng) tối đa 24 giờ, rồi mới bị huỷ.

## 2. Quy tắc an toàn (bắt buộc)

Runner chạy **mọi lệnh** trong `ci.yml` của bất kỳ ai push được vào repo.

- Chỉ cài runner **trong VM**. Không cài thẳng lên Windows hay macOS, không dùng WSL2 (WSL tự mount `C:`/`D:` nên job đọc
  được file cá nhân).
- VM **không** bật Shared Folders, Shared Clipboard, Drag and Drop. Không copy `.env`, SSH key cá nhân hay token cloud
  vào VM.
- Runner chạy bằng user `runner` **không có sudo**, chỉ thuộc nhóm `docker`.
- Token đăng ký do ban tổ chức cấp, **dùng một lần, hết hạn sau khoảng 1 giờ**. Không dán token vào file, commit, issue hay
  chat nhóm. Hết hạn thì xin token mới, không thử token khác.

## 3. Yêu cầu máy

| | Tối thiểu | Ghi chú |
|---|---|---|
| CPU | 4 nhân / 8 luồng, bật ảo hoá (VT-x / AMD-V) trong BIOS | VM dùng 2 vCPU |
| RAM | 12 GB | VM dùng 6 GB |
| Ổ trống | 50 GB | ISO ~3 GB + ổ ảo 40 GB |
| OS | Windows 10/11 x64 | macOS Apple Silicon: xem §8 |

## 4. Xin token (làm sau bước 6, không làm trước)

Nhắn ban tổ chức xin lệnh đăng ký runner cho repo `AI20K-Build-Phase-Cohort-5/P-019`, với:

- **Tên máy**: `team-19-<github-username>` (mỗi người một tên, không trùng).
- **Nhãn**: `team-19` (giữ đúng, nếu không job không vào máy).

Token **không phân biệt OS**. Lệnh ban tổ chức đưa có dạng `./config.cmd …` (Windows). Trên VM Linux chỉ cần đổi
`config.cmd` thành `config.sh`, giữ nguyên `--url --token --name --labels`.

## 5. Tạo VM và cài Ubuntu

1. Cài VirtualBox 7.2 (PowerShell): `winget install --id Oracle.VirtualBox --exact`, rồi bấm Yes ở hộp thoại UAC.
2. Tải **Ubuntu Server 24.04 LTS** (`ubuntu-24.04.x-live-server-amd64.iso`) từ `releases.ubuntu.com/24.04/`, kiểm tra
   SHA256 với file `SHA256SUMS` cùng thư mục: `Get-FileHash <file>.iso -Algorithm SHA256`.
3. VirtualBox → **New**:
   - Name `p019-runner`, chọn ISO vừa tải, **tick "Skip Unattended Installation"**. Bản cài tự động của VirtualBox không cài
     OpenSSH và dễ lỗi ở bước cuối.
   - Hardware: **2 CPU**, **6144 MB RAM**, bật EFI.
   - Hard disk: 40 GB, đặt trên ổ còn trống (ví dụ `D:\VMs`).
4. Settings của VM:
   - **General → Advanced**: Shared Clipboard = Disabled, Drag'n'Drop = Disabled.
   - **Shared Folders**: để trống.
   - **Network → Adapter 1**: NAT → **Port Forwarding** → thêm `ssh`, TCP, Host IP `127.0.0.1`, Host Port `2222`, Guest Port `22`.
5. Start VM và cài Ubuntu theo mặc định. Hai chỗ cần chú ý:
   - Profile: username `ci`, đặt mật khẩu mạnh và lưu trong trình quản lý mật khẩu.
   - Màn hình SSH: **tick "Install OpenSSH server"**.
6. Cài xong → Reboot → **Devices → Optical Drives → Remove disk** nếu ISO chưa tự tháo.

> **Đã gặp:** với 4 vCPU, VM treo ở `Loading essential drivers ...` khi máy có Hyper-V (Docker Desktop / WSL2 bật).
> Hạ xuống 2 vCPU là boot bình thường.

> **Hyper-V làm VM chậm.** Khi Docker Desktop / WSL2 bật Hyper-V, VirtualBox chạy qua lớp Hyper-V (chế độ NEM) nên chậm
> hơn nhiều. Nếu laptop đang bận, đồng hồ VM bị trễ (`VBox.log` có `TM: Giving up catch-up attempt at a 60 … ns lag`) và
> job hỏng vì timeout mạng (`EAI_AGAIN`). Khi bật runner: đóng bớt ứng dụng nặng. Kiểm tra máy có Hyper-V không:
> PowerShell `(Get-CimInstance Win32_ComputerSystem).HypervisorPresent` (True = có). Nếu không cần Docker Desktop / WSL2,
> tắt Hyper-V cho VM chạy nhanh: `bcdedit /set hypervisorlaunchtype off` (Admin) rồi khởi động lại; bật lại bằng
> `bcdedit /set hypervisorlaunchtype auto`.

## 6. Chuẩn bị Ubuntu

SSH vào VM từ PowerShell hoặc Git Bash: `ssh -p 2222 ci@127.0.0.1`, rồi chạy:

```bash
# DNS công cộng cho VM — DNS mạng trường/công ty hay chập chờn làm apt, Docker, runner lỗi "Could not resolve host"
sudo mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nDNS=1.1.1.1 8.8.8.8\nFallbackDNS=9.9.9.9\nDomains=~.\n' | sudo tee /etc/systemd/resolved.conf.d/public-dns.conf
sudo systemctl restart systemd-resolved

# Gói cơ bản + Docker Engine (cho job backend-postgres và docker-smoke)
sudo apt update && sudo apt -y upgrade
sudo apt -y install curl git unzip jq build-essential ca-certificates
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo docker run --rm hello-world        # phải in "Hello from Docker!"

# User riêng chạy runner: KHÔNG sudo, chỉ thuộc nhóm docker
sudo useradd -m -s /bin/bash runner
sudo usermod -aG docker runner

# Tải runner (giữ đúng phiên bản ban tổ chức đưa; runner tự cập nhật sau khi online)
sudo -u runner bash -c '
  mkdir -p ~/actions-runner && cd ~/actions-runner &&
  curl -fsSL -o runner.tar.gz https://github.com/actions/runner/releases/download/v2.336.0/actions-runner-linux-x64-2.336.0.tar.gz &&
  tar xzf runner.tar.gz && rm runner.tar.gz'
sudo /home/runner/actions-runner/bin/installdependencies.sh
```

Không cần cài Python hay Node: `setup-python` / `setup-node` trong CI tự tải bản theo `.python-version` và
`frontend/.nvmrc`.

## 7. Đăng ký runner và chạy nền

Đến đây mới xin token (§4), rồi chạy ngay:

```bash
cd /home/runner/actions-runner
sudo -u runner ./config.sh --url https://github.com/AI20K-Build-Phase-Cohort-5/P-019 \
  --token <TOKEN_BAN_TO_CHUC_CAP> --name team-19-<github-username> --labels team-19 --unattended
sudo ./svc.sh install runner
sudo ./svc.sh start
sudo ./svc.sh status                       # Active: active (running)
sudo journalctl -u 'actions.runner.*' -f   # chờ dòng "Listening for Jobs", Ctrl+C để thoát
```

- `config.sh` in `√ Runner successfully added` là đăng ký xong. Token hết tác dụng sau bước này, runner dùng
  credential riêng.
- Lần đầu có thể thấy `Socket Error: TryAgain`. Runner tự thử lại; nếu lặp mãi thì kiểm tra lại DNS ở §6.
- Kiểm tra online: repo → **Settings → Actions → Runners** (cần quyền admin, nếu không thì nhờ ban tổ chức xem).

## 8. Dùng hằng ngày

| Việc | Lệnh (PowerShell trên laptop) |
|---|---|
| Bật VM chạy nền, không mở cửa sổ | `& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" startvm p019-runner --type headless` |
| Tắt VM an toàn | `& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" controlvm p019-runner acpipowerbutton` |
| Xem trạng thái | `& "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" list runningvms` |

- Runner là service nên **tự online khi VM bật**, không cần đăng nhập vào VM.
- **Không tắt VM bằng Power Off khi đang có job chạy.** Tắt ngang lúc `setup-python` / `setup-node` đang giải nén sẽ để lại
  bản Python/Node hỏng trong toolcache (xem §10). Tắt bằng `acpipowerbutton` khi runner rảnh.
- Không để laptop Sleep khi đang bật runner: Settings → System → Power → *When plugged in … sleep* → Never.
- Dọn đĩa VM khi gần đầy: `docker system prune -af` (với user `ci` qua sudo, hoặc user `runner`).

**macOS Apple Silicon:** VirtualBox chưa ổn định trên ARM. Dùng UTM hoặc Multipass với Ubuntu 24.04 **ARM64**, các bước
§6–§7 giữ nguyên, chỉ đổi gói runner thành `actions-runner-linux-arm64-<phiên bản>.tar.gz`.

## 9. Gỡ runner

- Ngừng tạm thời: tắt VM. Job sẽ đi sang các runner khác.
- Gỡ hẳn (ví dụ rời nhóm, đổi máy): xin ban tổ chức **removal token**, rồi
  `sudo ./svc.sh stop && sudo ./svc.sh uninstall && sudo -u runner ./config.sh remove --token <REMOVAL_TOKEN>`.
  Sau đó có thể xoá VM trong VirtualBox (Remove → Delete all files).

## 10. Lỗi đã gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| VM treo ở `Loading essential drivers ...` | 4 vCPU trên máy có Hyper-V | Hạ còn 2 vCPU |
| `Could not resolve host: get.docker.com` / `download.docker.com` | DNS mạng chập chờn | Đặt DNS công cộng (§6) |
| Cài tự động báo lỗi ở `vboxpostinstall.sh` | Post-install command của VirtualBox chạy trong hệ thống đích, không có `/target` | Bỏ cài tự động, cài tay và tick OpenSSH (§5) |
| `Host key verification failed` khi SSH | Lần đầu đã lưu host key của bộ cài, không phải của hệ thống thật | `ssh-keygen -R "[127.0.0.1]:2222"` rồi SSH lại |
| Job đứng Queued mãi | Không runner `team-19` nào online, hoặc sai nhãn | Bật VM; kiểm tra nhãn trong lệnh `config.sh` |
| Đồng hồ VM trễ, job lỗi `EAI_AGAIN` / `Resource temporarily unavailable` | VM thiếu CPU (Hyper-V + laptop bận) | Đóng bớt ứng dụng; xem cảnh báo Hyper-V ở §5 |
| `ruff: command not found` / `alembic: command not found` dù bước `pip install` xanh; Python báo `init_fs_encoding … can't find encoding` | Toolcache Python bị giải nén dở (VM tắt ngang) nhưng đã đánh dấu xong | Trong VM: `sudo -u runner rm -rf /home/runner/actions-runner/_work/_tool/Python/<phiên bản>` rồi chạy lại job |
| `npm ci` báo `package.json and package-lock.json … are not in sync`, `Missing: @emnapi/…` | Lockfile sinh bằng npm 11 (Node 26), CI dùng Node 22 / npm 10 | Sinh lại lockfile bằng Node 22 (`frontend/.nvmrc`): `nvm use 22` rồi `npm install`, commit `package-lock.json` |
