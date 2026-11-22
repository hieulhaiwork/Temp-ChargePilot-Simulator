"use client";

/**
 * S1 — đăng nhập (FR1). Không có nút chọn vai trò: vai trò lấy từ TokenResponse.role của backend,
 * rồi điều hướng cư dân → S2, vận hành → S5 (docs/plan/00-overview.md Q4).
 */
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ErrorPanel } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { homePathFor, setSession } from "@/lib/auth/session";

/** Chỉ nhận đường dẫn nội bộ ở tham số ?next= — không chuyển hướng ra site khác. */
function safeNextPath(): string | null {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/login", { body: { email, password } })),
    onSuccess: (token) => {
      setSession({
        token: token.access_token,
        role: token.role,
        userId: token.user_id,
        displayName: token.display_name,
      });
      const next = safeNextPath();
      const home = homePathFor(token.role);
      router.replace(next && next.startsWith(home) ? next : home);
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    login.mutate();
  }

  const wrongPassword = login.error instanceof ApiError && login.error.status === 401;
  const ready = email.trim() !== "" && password !== "";

  return (
    <form onSubmit={onSubmit} className="stack" style={{ gap: 16 }} noValidate>
      <div className="field">
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          type="email"
          name="email"
          autoComplete="username"
          maxLength={254}
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="login-password">Mật khẩu</label>
        <input
          id="login-password"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          aria-invalid={wrongPassword || undefined}
          aria-describedby="login-why"
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      <div>
        <button type="submit" disabled={login.isPending || !ready} className="btn btn-primary" style={{ width: "100%" }}>
          {login.isPending ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
        <span id="login-why" className="hint" style={{ display: "block", marginTop: 6 }}>
          {!ready ? "Nhập email và mật khẩu để đăng nhập." : ""}
        </span>
      </div>
      {login.isError ? (
        login.error instanceof ApiError && login.error.isNotImplemented ? (
          <NotImplementedPanel
            endpoint="POST /api/v1/auth/login"
            taskId={login.error.taskId}
            detail={login.error.detail}
          />
        ) : wrongPassword ? (
          <div role="alert" className="notice notice-bad">
            <div>
              <strong>Email hoặc mật khẩu chưa đúng.</strong>
              <p>Kiểm tra rồi thử lại.</p>
            </div>
          </div>
        ) : (
          <ErrorPanel error={login.error} />
        )
      ) : null}
    </form>
  );
}
