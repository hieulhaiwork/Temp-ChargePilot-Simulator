"use client";

/**
 * Khung chung của một vai trò — nối WebSocket MỘT lần ở đây và chia sẻ trạng thái qua StreamContext.
 *   Cư dân   (mockup docs/mockups/cu-dan): sidebar trái trên máy tính, thanh điều hướng dưới trên điện thoại.
 *   Vận hành (mockup docs/mockups/van-hanh, RoleShell của nhánh buivanlam): header ngang có tab, máy tính 1280 px+.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { queries } from "@/lib/api/queries";
import { clearSession, useSession, type Role } from "@/lib/auth/session";
import { StreamContext, useStream } from "@/lib/ws/useStream";

import { LiveIndicator } from "./LiveIndicator";

type NavItem = { href: string; label: string; icon: IconName; mobile?: boolean };

const RESIDENT_NAV: NavItem[] = [
  { href: "/resident", label: "Trang chủ", icon: "home", mobile: true },
  { href: "/resident/book", label: "Đặt lịch", icon: "calendar", mobile: true },
  { href: "/resident/plan", label: "Lịch sạc", icon: "activity" },
  { href: "/resident/map", label: "Sơ đồ bãi", icon: "map", mobile: true },
  { href: "/resident/notifications", label: "Thông báo", icon: "bell", mobile: true },
  { href: "/resident/profile", label: "Hồ sơ", icon: "user", mobile: true },
];

const OPERATOR_NAV: NavItem[] = [
  { href: "/operator", label: "Dashboard", icon: "gauge" },
  { href: "/operator/map", label: "Sơ đồ bãi", icon: "map" },
  { href: "/operator/schedule", label: "Hàng đợi & lịch", icon: "queue" },
  { href: "/operator/approvals", label: "Duyệt lệnh", icon: "shield" },
  { href: "/operator/simulation", label: "Mô phỏng", icon: "flask" },
];

/** Mục đang mở: khớp chính xác, hoặc là trang con (trừ trang chủ của vai trò). */
function isActive(pathname: string, href: string, home: string): boolean {
  if (href === home) return pathname === home;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Brand({ caption }: { caption: string }) {
  return (
    <span className="brand">
      <span className="brand-glyph">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path fill="currentColor" d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
        </svg>
      </span>
      <span>
        ChargePilot
        <small>{caption}</small>
      </span>
    </span>
  );
}

function ResidentShell({ children }: { children: ReactNode }) {
  const session = useSession();
  const pathname = usePathname();
  const stream = useStream("resident");
  const current = RESIDENT_NAV.find((item) => isActive(pathname, item.href, "/resident"));

  return (
    <StreamContext.Provider value={stream}>
      <a href="#main" className="skip">
        Bỏ qua tới nội dung chính
      </a>
      <div className="rs-layout">
        <aside className="rs-sidebar">
          <Link href="/resident" aria-label="ChargePilot, Trang chủ">
            <Brand caption="Cổng cư dân" />
          </Link>
          <nav className="rs-nav" aria-label="Điều hướng chính">
            {RESIDENT_NAV.map((item) => (
              <Link key={item.href} href={item.href} aria-current={item === current ? "page" : undefined}>
                <Icon name={item.icon} />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="rs-side-bottom">
            <span>
              <b>{session?.displayName ?? "Cư dân"}</b>
              <span className="hint" style={{ display: "block" }}>
                Cư dân
              </span>
            </span>
            <button type="button" onClick={clearSession} className="btn btn-secondary small">
              <Icon name="exit" />
              Đăng xuất
            </button>
          </div>
        </aside>
        <div style={{ minWidth: 0 }}>
          <header className="rs-topbar">
            <span className="desktop-only hint">
              Cổng cư dân › <b style={{ color: "var(--ink)" }}>{current?.label ?? "Trang chủ"}</b>
            </span>
            <span className="mobile-only">
              <Brand caption="Cổng cư dân" />
            </span>
            {/* Trên điện thoại, Đăng xuất nằm ở trang Hồ sơ (mockup cu-dan) để topbar không tràn ngang. */}
            <LiveIndicator state={stream} />
          </header>
          <main id="main" tabIndex={-1} className="rs-main">
            {children}
            <p className="footnote">
              <Icon name="info" />
              Hệ thống mô phỏng · Giờ trạm GMT+7
            </p>
          </main>
        </div>
      </div>
      <nav className="rs-bottomnav" aria-label="Điều hướng trên điện thoại">
        {RESIDENT_NAV.filter((item) => item.mobile).map((item) => (
          <Link key={item.href} href={item.href} aria-current={item === current ? "page" : undefined}>
            <Icon name={item.icon} />
            {item.label}
          </Link>
        ))}
      </nav>
    </StreamContext.Provider>
  );
}

function OperatorShell({ children }: { children: ReactNode }) {
  const session = useSession();
  const pathname = usePathname();
  const stream = useStream("operator");
  // Số đề nghị chờ duyệt trên tab: chỉ hiện khi API trả được (hôm nay còn 501 → không hiện số giả).
  const approvals = useQuery(queries.operatorApprovals());
  const pending = approvals.data?.filter((a) => a.status === "pending").length ?? 0;

  return (
    <StreamContext.Provider value={stream}>
      <a href="#main" className="skip">
        Bỏ qua tới nội dung chính
      </a>
      <div className="op">
        <div className="op-sticky">
          <header className="op-head">
          <div className="op-left">
            <Link href="/operator" aria-label="ChargePilot Vận hành, Dashboard">
              <Brand caption="Control Center · Vận hành" />
            </Link>
            <nav className="op-tabs" aria-label="Điều hướng chính">
              {OPERATOR_NAV.map((item) => {
                const active = isActive(pathname, item.href, "/operator");
                const badge = item.href === "/operator/approvals" && pending > 0 ? pending : null;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    aria-label={badge ? `${item.label}, ${badge} đề nghị chờ duyệt` : undefined}
                  >
                    <Icon name={item.icon} />
                    {item.label}
                    {badge ? <span className="tag tag-gold" style={{ padding: "0 6px" }}>{badge}</span> : null}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="op-who">
            <LiveIndicator state={stream} />
            <span>
              <b>{session?.displayName ?? "Vận hành"}</b>
              <span className="hint" style={{ display: "block" }}>
                Vận hành trạm
              </span>
            </span>
            <button type="button" onClick={clearSession} className="btn btn-secondary small">
              Đăng xuất
            </button>
          </div>
          </header>
        </div>
        <main id="main" tabIndex={-1} className="op-main">
          {children}
          <p className="footnote">
            <Icon name="info" />
            Hệ thống mô phỏng · Giờ trạm GMT+7 · Mọi lệnh tới trạm đi qua Guard
          </p>
        </main>
      </div>
    </StreamContext.Provider>
  );
}

export function RoleShell({ role, children }: { role: Role; children: ReactNode }) {
  return role === "resident" ? <ResidentShell>{children}</ResidentShell> : <OperatorShell>{children}</OperatorShell>;
}
