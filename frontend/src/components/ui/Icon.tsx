/** Bộ icon nét (24 × 24) — cùng nguồn với docs/mockups/cu-dan/assets/kit.js. Luôn đi kèm chữ, không đứng một mình. */

const GLYPHS = {
  home: "<path d='m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z'/>",
  calendar: "<rect x='3' y='5' width='18' height='16' rx='3'/><path d='M7 3v4m10-4v4M3 10h18m-12 5 2 2 4-4'/>",
  activity: "<path d='M3 12h4l3-7 4 14 3-7h4'/>",
  bell: "<path d='M18 8a6 6 0 0 0-12 0c0 7-3 8-3 10h18c0-2-3-3-3-10m-12 0M10 21h4'/>",
  user: "<circle cx='12' cy='8' r='3.5'/><path d='M4.5 21v-2a7.5 6 0 0 1 15 0v2'/>",
  adjust: "<path d='M3 7h8m4 0h6M3 17h3m4 0h11'/><circle cx='13' cy='7' r='2.2'/><circle cx='8' cy='17' r='2.2'/>",
  pin: "<path d='M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z'/><circle cx='12' cy='10' r='2.5'/>",
  chev: "<path d='m9 5 7 7-7 7'/>",
  arrow: "<path d='M4 12h16m-6-6 6 6-6 6'/>",
  back: "<path d='M20 12H4m6-6-6 6 6 6'/>",
  check: "<path d='m4.5 12.5 5 5L20 7'/>",
  clock: "<circle cx='12' cy='12' r='8.8'/><path d='M12 7v5l3 2'/>",
  plug: "<path d='M8 3v5m8-5v5M6 8h12v2a6 6 0 0 1-12 0V8Zm6 8v5'/>",
  bolt: "<path d='m13 2-9 12h7l-1 8 10-13h-7l1-7Z'/>",
  chat: "<path d='M21 11a8.5 8.5 0 0 1-9 8 12 12 0 0 1-3-.4L4 21l1-5a8 8 0 0 1-2-5 8.5 8.5 0 0 1 9-8 8.5 8.5 0 0 1 9 8Z'/><path d='M8 11h.01M12 11h.01M16 11h.01'/>",
  info: "<circle cx='12' cy='12' r='9'/><path d='M12 11v5m0-8h.01'/>",
  battery: "<rect x='2' y='7' width='17' height='10' rx='2'/><path d='M22 10v4M5 10v4m3-4v4'/>",
  car: "<path d='m4 11 2-5h11l3 5M4 11h16l1 3v4H3v-4l1-3Zm1 7v2m14-2v2M6 14h2m8 0h2'/>",
  layers: "<path d='m3 8 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 17l9 5 9-5'/>",
  shield: "<path d='m12 2 8 4v5c0 5-4 9-8 11-4-2-8-6-8-11V6l8-4Z'/><path d='m8 12 3 3 5-6'/>",
  alert: "<path d='m12 3 10 17H2L12 3Z'/><path d='M12 9v5m0 3h.01'/>",
  close: "<path d='m6 6 12 12m0-12L6 18'/>",
  refresh: "<path d='M20.5 10a8.5 8.5 0 1 0-1 8M21 4v6h-6'/>",
  queue: "<path d='M8 6h12M8 12h12M8 18h12M3 6h.01M3 12h.01M3 18h.01'/>",
  trash: "<path d='M3 6h18M9 6V4h6v2m-10 0 1 15h12l1-15m-9 4v7m4-7v7'/>",
  exit: "<path d='M9 4H4v16h5m0-8h12m-5-5 5 5-5 5'/>",
  checkcircle: "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 5-6'/>",
  book: "<path d='M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3V4Z'/>",
  wifi: "<path d='M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0m-11 4a6 6 0 0 1 8 0m-5 4h2'/>",
  gauge: "<path d='M3.5 16a8.5 8.5 0 1 1 17 0'/><path d='m12 16 4-5'/><circle cx='12' cy='16' r='1.4'/>",
  map: "<path d='M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Zm0 0v14m6-12v14'/>",
  flask: "<path d='M9 3h6m-5 0v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M7.5 15h9'/>",
  pause: "<path d='M8 5v14m8-14v14'/>",
  play: "<path d='m7 4 13 8-13 8V4Z'/>",
  ban: "<circle cx='12' cy='12' r='9'/><path d='m5.6 5.6 12.8 12.8'/>",
  grid: "<rect x='3' y='3' width='7' height='7' rx='1.5'/><rect x='14' y='3' width='7' height='7' rx='1.5'/><rect x='3' y='14' width='7' height='7' rx='1.5'/><rect x='14' y='14' width='7' height='7' rx='1.5'/>",
  chart: "<path d='M3 3v18h18'/><path d='m7 15 4-5 3 3 5-7'/>",
  eye: "<path d='M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z'/><circle cx='12' cy='12' r='3'/>",
  spark: "<path d='M12 3c.8 5.8 3 8.1 8 9-5 .9-7.2 3.2-8 9-.8-5.8-3-8.1-8-9 5-.9 7.2-3.2 8-9Z'/><path d='M20 2v4m-2-2h4'/>",
  moon: "<path d='M20.5 15.2A9 9 0 0 1 8.8 3.5 9 9 0 1 0 20.5 15.2Z'/>",
  download: "<path d='M12 3v12m-5-5 5 5 5-5M4 20h16'/>",
  sun: "<circle cx='12' cy='12' r='4'/><path d='M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2'/>",
  wallet: "<rect x='3' y='6' width='18' height='14' rx='2'/><path d='m4 6 13-3 1 3m3 5h-6v4h6'/>",
  mail: "<rect x='3' y='5' width='18' height='14' rx='2'/><path d='m4 7 8 6 8-6'/>",
} as const;

export type IconName = keyof typeof GLYPHS;

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg
      className={`ico ${className}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: GLYPHS[name] }}
    />
  );
}
