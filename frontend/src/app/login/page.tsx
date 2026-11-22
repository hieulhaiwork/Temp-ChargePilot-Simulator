import { LoginForm } from "@/components/auth/LoginForm";

/**
 * S1 · Đăng nhập (mockup docs/mockups/login.html). Banner ở layout gốc đã gọi /health để đánh thức backend
 * trong lúc người dùng gõ. Vai trò lấy từ TokenResponse.role, không có nút chọn vai trò.
 */
export default function LoginPage() {
  return (
    <div className="login">
      <aside className="login-art" aria-hidden="true">
        <h2>Sạc đủ trước giờ đi, không vượt giới hạn của khu.</h2>
        <p>ChargePilot xếp lịch sạc cho bãi xe cư dân. Mọi lệnh tới trạm đều qua lớp kiểm soát an toàn.</p>
      </aside>
      <main id="main" className="login-side">
        <div className="login-card">
          <span className="brand">
            <span className="brand-glyph">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
              </svg>
            </span>
            ChargePilot
          </span>
          <div>
            <h1>Đăng nhập</h1>
            <p className="subcopy" style={{ marginTop: 8 }}>
              Dùng tài khoản cư dân hoặc vận hành trạm. Đây là hệ thống mô phỏng, dữ liệu không phải của trạm sạc thật.
            </p>
          </div>
          <LoginForm />
        </div>
      </main>
    </div>
  );
}
