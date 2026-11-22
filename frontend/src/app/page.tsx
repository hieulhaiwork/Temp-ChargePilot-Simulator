"use client";

/** "/" — chuyển hướng theo phiên: chưa đăng nhập → S1; cư dân → S2; vận hành → S5. */
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { homePathFor, useSession } from "@/lib/auth/session";

export default function HomePage() {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session === undefined) return;
    router.replace(session ? homePathFor(session.role) : "/login");
  }, [session, router]);

  return (
    <p role="status" className="p-4 text-sm text-neutral-600">
      Đang mở ChargePilot…
    </p>
  );
}
