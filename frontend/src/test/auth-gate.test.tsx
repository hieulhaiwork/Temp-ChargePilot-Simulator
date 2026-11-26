import { cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@/components/auth/AuthGate";
import { clearSession, setSession } from "@/lib/auth/session";

import nextConfig from "../../next.config";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

describe("AuthGate & Next.js instant validation config", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    clearSession();
  });

  afterEach(() => {
    cleanup();
    clearSession();
  });

  it("pins instantInsights validationLevel to manual-warning while AuthGate gates client routes", () => {
    expect(nextConfig.cacheComponents).toBe(true);
    expect(nextConfig.partialPrefetching).toBe(true);
    expect(nextConfig.experimental?.instantInsights?.validationLevel).toBe("manual-warning");
  });

  it("does not render protected children during SSR prerender", () => {
    const html = renderToString(
      <AuthGate role="resident">
        <div>Nội dung cư dân</div>
      </AuthGate>,
    );
    expect(html).toContain("Đang kiểm tra phiên đăng nhập");
    expect(html).not.toContain("Nội dung cư dân");
  });

  it("redirects unauthenticated users to /login without rendering children", () => {
    render(
      <AuthGate role="resident">
        <div>Nội dung cư dân</div>
      </AuthGate>,
    );
    expect(screen.queryByText("Nội dung cư dân")).toBeNull();
    expect(replaceMock).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?next=/));
  });

  it("blocks wrong role with alert and renders children only for matching role", () => {
    setSession({ token: "t-op", role: "operator", userId: "op-1", displayName: "Vận hành" });
    const { rerender } = render(
      <AuthGate role="resident">
        <div>Nội dung cư dân</div>
      </AuthGate>,
    );
    expect(screen.getByRole("alert").textContent).toContain("không có quyền");
    expect(screen.queryByText("Nội dung cư dân")).toBeNull();

    setSession({ token: "t-res", role: "resident", userId: "res-1", displayName: "Cư dân" });
    rerender(
      <AuthGate role="resident">
        <div>Nội dung cư dân</div>
      </AuthGate>,
    );
    expect(screen.getByText("Nội dung cư dân")).toBeTruthy();
  });
});
