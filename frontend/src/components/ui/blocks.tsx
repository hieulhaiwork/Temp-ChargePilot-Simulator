/**
 * Khối giao diện dùng chung của template "Forest & Amber" — mỗi component là một class trong globals.css
 * và một helper cùng tên trong mockup (docs/mockups/cu-dan/assets/kit.js: panel, title, head, tag, note).
 */
import { useId, type ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type Tone = "good" | "gold" | "neutral" | "bad" | "blue";

export function Panel({
  children,
  className = "",
  label,
  dark = false,
}: {
  children: ReactNode;
  className?: string;
  /** Tên vùng cho trình đọc màn hình khi khối không có tiêu đề riêng. */
  label?: string;
  dark?: boolean;
}) {
  return (
    <section aria-label={label} className={`panel ${dark ? "dark" : ""} ${className}`}>
      {children}
    </section>
  );
}

export function SectionHead({
  title,
  icon,
  sub,
  extra,
  level = 2,
}: {
  title: ReactNode;
  icon?: IconName;
  sub?: ReactNode;
  extra?: ReactNode;
  level?: 2 | 3;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className="section-head">
      <div>
        <div className="section-name">
          {icon ? <Icon name={icon} /> : null}
          <Heading>{title}</Heading>
        </div>
        {sub ? <p>{sub}</p> : null}
      </div>
      {extra}
    </div>
  );
}

export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="pagehead">
      <div>
        <h1>{title}</h1>
        {sub ? <p>{sub}</p> : null}
      </div>
      {actions ? <div className="actions" style={{ marginTop: 0 }}>{actions}</div> : null}
    </div>
  );
}

export function Tag({ children, tone = "neutral", icon }: { children: ReactNode; tone?: Tone; icon?: IconName }) {
  return (
    <span className={`tag tag-${tone}`}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </span>
  );
}

export function Notice({
  title,
  children,
  tone = "neutral",
  icon = "info",
  role,
}: {
  title: ReactNode;
  children?: ReactNode;
  tone?: "neutral" | "gold" | "bad" | "good";
  icon?: IconName;
  role?: "status" | "alert";
}) {
  return (
    <div role={role} className={`notice ${tone === "neutral" ? "" : `notice-${tone}`}`}>
      <Icon name={icon} />
      <div>
        <strong>{title}</strong>
        {children ? <div className="notice-body">{children}</div> : null}
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty-card">
      <span className="slab-icon">
        <Icon name={icon} />
      </span>
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div role="status" aria-label="Đang tải">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="sk" />
      ))}
      <span className="sk short" />
    </div>
  );
}

export function KeyValues({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v], i) => (
        <div key={i} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Thanh đo tỉ lệ có nhãn chữ cho trình đọc màn hình. */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  const tone = ratio >= 0.95 ? "full" : ratio >= 0.8 ? "warn" : "";
  return (
    <div className={`bar ${tone}`} role="img" aria-label={`${label}: ${Math.round(ratio * 100)}%`}>
      <i style={{ width: `${ratio * 100}%` }} />
    </div>
  );
}

/** Thao tác đã có hợp đồng API nhưng màn chưa nối: nút khoá kèm lý do bằng chữ (không ẩn nút). */
export function PendingAction({ label, task, icon }: { label: string; task: string; icon?: IconName }) {
  const id = useId();
  return (
    <span>
      <button type="button" className="btn btn-secondary" disabled aria-describedby={id}>
        {icon ? <Icon name={icon} /> : null}
        {label}
      </button>
      <span className="hint" id={id} style={{ display: "block", marginTop: 4 }}>
        Chưa nối API · {task}
      </span>
    </span>
  );
}
