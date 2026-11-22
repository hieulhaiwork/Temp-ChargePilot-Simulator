import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { BackendStatusBanner } from "@/components/system/BackendStatusBanner";
import { Providers } from "@/components/system/Providers";

import "./globals.css";

/* Be Vietnam Pro (OFL, xem fonts/FONT-LICENSE.txt) đặt trong repo — không tải phông từ bên ngoài lúc build/chạy. */
const beVietnam = localFont({
  src: [
    { path: "./fonts/BeVietnamPro-Regular.woff", weight: "400", style: "normal" },
    { path: "./fonts/BeVietnamPro-SemiBold.woff", weight: "600", style: "normal" },
    { path: "./fonts/BeVietnamPro-Bold.woff", weight: "700", style: "normal" },
  ],
  variable: "--font-be-vietnam",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ChargePilot",
  description: "Quản lý và tối ưu lịch sạc xe điện cho bãi sạc khu chung cư (mô phỏng — đề tài SC-16, nhóm T019).",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#163d34" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={`${beVietnam.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Providers>
          <BackendStatusBanner />
          {children}
        </Providers>
      </body>
    </html>
  );
}
