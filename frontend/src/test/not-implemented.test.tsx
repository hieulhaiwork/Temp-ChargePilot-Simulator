import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { DataBlock } from "@/components/system/DataBlock";
import { errorMessage } from "@/components/system/ErrorPanel";
import { NotImplementedPanel } from "@/components/system/NotImplementedPanel";
import { toApiError } from "@/lib/api/errors";

afterEach(cleanup);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("màn hình khi backend trả 501 (ADR-004)", () => {
  it("NotImplementedPanel hiện task ID và endpoint", () => {
    render(<NotImplementedPanel endpoint="GET /api/v1/resident/queue" taskId="T2.2" detail="[T2.2] queue_status" />);
    expect(screen.getByRole("status").textContent).toContain("task T2.2");
    expect(screen.getByText("GET /api/v1/resident/queue")).toBeTruthy();
  });

  it("DataBlock chuyển lỗi 501 thành NotImplementedPanel, không báo lỗi đỏ", async () => {
    const failing = {
      queryKey: ["test", "queue"],
      queryFn: async (): Promise<unknown> => {
        throw toApiError(501, { detail: "[T2.2] queue_status", code: "not_implemented", task_id: "T2.2" });
      },
    };
    render(
      <DataBlock endpoint="GET /api/v1/resident/queue" query={failing}>
        {() => <p>dữ liệu</p>}
      </DataBlock>,
      { wrapper },
    );
    expect(await screen.findByText(/Chức năng này chưa được cài đặt/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("DataBlock hiện lỗi khác bằng ErrorPanel kèm nút thử lại", async () => {
    const failing = {
      queryKey: ["test", "forbidden"],
      queryFn: async (): Promise<unknown> => {
        throw toApiError(403, { detail: "Cần vai trò operator", code: "forbidden" });
      },
    };
    render(
      <DataBlock endpoint="GET /api/v1/operator/station" query={failing}>
        {() => <p>dữ liệu</p>}
      </DataBlock>,
      { wrapper },
    );
    expect((await screen.findByRole("alert")).textContent).toContain("không có quyền");
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeTruthy();
  });

  it("DataBlock render dữ liệu bằng children khi thành công", async () => {
    const ok = { queryKey: ["test", "ok"], queryFn: async () => ({ power_limit_kw: 35 }) };
    render(
      <DataBlock endpoint="GET /api/v1/station/config" query={ok}>
        {(config) => <p>Giới hạn {config.power_limit_kw} kW</p>}
      </DataBlock>,
      { wrapper },
    );
    expect(await screen.findByText("Giới hạn 35 kW")).toBeTruthy();
  });
});

describe("thông điệp lỗi cho người dùng", () => {
  it("llm_unavailable gợi ý dùng form (NFR khả dụng)", () => {
    expect(errorMessage(toApiError(503, { detail: "x", code: "llm_unavailable" }))).toContain("form");
  });

  it("mã không có trong bảng thì dùng detail của backend", () => {
    expect(errorMessage(toApiError(404, { detail: "Không có kịch bản 'x'", code: "not_found" }))).toBe(
      "Không có kịch bản 'x'",
    );
  });
});
