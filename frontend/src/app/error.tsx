"use client";

/** Lỗi không lường trước khi render một trang — khối dữ liệu tự xử lý lỗi API của mình, không rơi vào đây. */
export default function RouteError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main role="alert" className="mx-auto flex w-full max-w-sm flex-col gap-3 p-4">
      <h1 className="text-xl font-semibold">Trang gặp lỗi</h1>
      <p className="text-sm">Vui lòng thử lại. Nếu vẫn lỗi, tải lại trang.</p>
      <button type="button" onClick={reset} className="min-h-11 rounded border border-neutral-500 px-3">
        Thử lại
      </button>
    </main>
  );
}
