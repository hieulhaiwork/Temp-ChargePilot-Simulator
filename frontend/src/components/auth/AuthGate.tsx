"use client";

/**
 * Cổng theo vai trò cho /resident/* và /operator/*. Chỉ là TRẢI NGHIỆM người dùng: phân quyền thật
 * nằm ở backend (401/403) — ai sửa sessionStorage cũng không đọc được dữ liệu của vai trò khác.
 */
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { homePathFor, useSession, type Role } from "@/lib/auth/session";

export function AuthGate({ role, children }: { role: Role; children: ReactNode }) {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session === null) {
      // Đọc đường dẫn ngay trong effect (không dùng usePathname) để layout vẫn prerender được.
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [session, router]);

  if (session === undefined) {
    return (
      <p role="status" className="p-4 text-sm text-neutral-600">
        Đang kiểm tra phiên đăng nhập…
      </p>
    );
  }
  if (session === null) return null; // đang chuyển về /login

  if (session.role !== role) {
    return (
      <div role="alert" className="m-4 rounded border border-red-400 bg-red-50 p-3 text-sm text-red-900">
        <p>Bạn không có quyền xem trang này.</p>
        <a href={homePathFor(session.role)} className="mt-2 inline-block underline">
          Về trang của tôi
        </a>
      </div>
    );
  }
  return <>{children}</>;
}
