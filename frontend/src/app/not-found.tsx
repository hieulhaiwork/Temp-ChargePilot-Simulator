import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-col gap-3 p-4">
      <h1 className="text-xl font-semibold">Không tìm thấy trang</h1>
      <Link href="/" className="underline">
        Về trang chủ
      </Link>
    </main>
  );
}
