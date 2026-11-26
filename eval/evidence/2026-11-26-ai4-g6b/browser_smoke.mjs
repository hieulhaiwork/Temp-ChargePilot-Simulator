import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const toolkit = process.argv[2];
assert.ok(toolkit, "Pass the temporary Playwright installation directory");
const { chromium } = await import(pathToFileURL(resolve(toolkit, "node_modules/playwright/index.mjs")).href);
const base = process.argv[3] ?? "http://localhost:3019";
const browser = await chromium.launch({ headless: true });

async function login(page, role, user) {
  await page.goto(`${base}/login`);
  await page.getByLabel("Email").fill(`${user}@g6a.example`);
  await page.getByLabel("Mật khẩu").fill("fixture-only-passphrase");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL(`**/${role}`);
  const panel = page.getByRole("region", { name: "Trợ lý sạc" });
  await panel.waitFor();
  return panel;
}

async function ask(page, panel, question) {
  await panel.getByRole("textbox", { name: "Tin nhắn cho Trợ lý sạc" }).fill(question);
  const received = page.waitForResponse((response) => response.url().endsWith("/api/v1/chat/stream"));
  await panel.getByRole("button", { name: "Gửi", exact: true }).click();
  const response = await received;
  assert.equal(response.status(), 200);
  const events = (await response.text()).split("\n").filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice(6)));
  assert.ok(events.some((event) => event.type === "status"));
  assert.equal(events.at(-1).type, "done");
  assert.equal(await panel.getByRole("button", { name: /áp dụng/i }).count(), 0);
  return events.at(-1).data;
}

async function completed(page, panel, question, capability) {
  const polled = page.waitForResponse(async (response) => {
    if (!response.url().includes("/api/v1/chat/sessions/") || !response.url().includes("/jobs/") || !response.ok()) return false;
    return (await response.json()).job.status === "succeeded";
  });
  const turn = await ask(page, panel, question);
  assert.ok(turn.advisory.some((item) => item.kind === "job"));
  const job = (await (await polled).json()).job;
  assert.equal(job.job_kind, capability);
  assert.equal(job.result.result.applied, false);
  await panel.getByRole("region", { name: capability === "how_to" ? "Kết quả HOW-TO" : "Kết quả WHAT-IF" }).waitFor();
  return { turn, job };
}

async function rankedOptions() {
  const page = await browser.newPage();
  const panel = await login(page, "operator", "operator");
  const result = await completed(
    page, panel,
    "Vì sao các xe bị trễ và cần nguồn điện bao nhiêu để đáp ứng các cam kết? Thử 22 đến 106 kW, giữ các xe AC đúng hạn.",
    "how_to",
  );
  assert.equal(result.job.result.result.options[0].value, 94);
  assert.equal(result.job.result.result.search_status, "partial");
  await panel.getByRole("region", { name: "Kết quả HOW-TO" }).getByText("94 kW đầu vào lưới · Khả thi", { exact: true }).waitFor();
  console.log(JSON.stringify({ browser: browser.version(), provider: "scripted fixture", result }, null, 2));
}

async function twoRoles() {
  const residentPage = await browser.newPage();
  const resident = await login(residentPage, "resident", "res-resident-demo");
  const residentWhy = await ask(residentPage, resident, "Vì sao xe tôi đang chờ?");
  assert.ok(residentWhy.advisory[0].claims.length > 0);
  await resident.getByRole("region", { name: "Kết quả WHY" }).waitFor();
  const residentWhatIf = await completed(residentPage, resident, "Xem xe tôi xoay xở ra sao với mục tiêu 75%.", "what_if");
  const row = residentWhatIf.job.result.result.affected_vehicles[0];
  assert.equal(row.baseline_original.target_soc, 90);
  assert.equal(row.patched_revised.target_soc, 75);
  await new Promise((resolve) => setTimeout(resolve, 15000));
  const residentCompound = await completed(
    residentPage, resident,
    "Tôi cần đi sau 70 phút, thử mức từ 65% đến 75%. Vì sao xe tôi đang chờ và có phương án nào tốt hơn không? Tôi đồng ý giảm mục tiêu. Tôi đồng ý mất cam kết gốc. Giữ nguyên hoặc rút ngắn hạn.",
    "how_to",
  );
  assert.deepEqual(residentCompound.turn.advisory.map((item) => item.kind), ["why", "job"]);
  await resident.getByRole("link", { name: "Mở lịch sạc để yêu cầu chỉnh sửa" }).waitFor();
  await residentPage.getByRole("button", { name: /đăng xuất/i }).first().click();
  await residentPage.waitForURL((url) => url.pathname === "/login");
  const nextResident = await login(residentPage, "resident", "second-resident");
  assert.equal(await nextResident.getByRole("region", { name: "Kết quả WHY" }).count(), 0);
  assert.equal(await nextResident.getByRole("region", { name: "Kết quả WHAT-IF" }).count(), 0);
  assert.equal(await nextResident.getByRole("region", { name: "Kết quả HOW-TO" }).count(), 0);

  const operatorPage = await browser.newPage();
  const operator = await login(operatorPage, "operator", "operator");
  const operatorCompound = await completed(
    operatorPage, operator,
    "Vì sao các xe bị trễ và cần nguồn điện bao nhiêu để đáp ứng các cam kết? Thử 22 đến 106 kW, giữ các xe AC đúng hạn.",
    "how_to",
  );
  await operator.getByRole("region", { name: "Kết quả WHY" }).waitFor();
  assert.deepEqual(operatorCompound.turn.advisory.map((item) => item.kind), ["why", "job"]);
  assert.notEqual(operatorCompound.job.result.result.search_status, "unsupported");
  assert.equal(await operator.getByRole("button", { name: /xác nhận lịch|áp dụng/i }).count(), 0);
  await new Promise((resolve) => setTimeout(resolve, 15000));
  const operatorWhatIf = await completed(
    operatorPage, operator,
    "Xem bãi xoay xở thế nào với nguồn 50 kW, dùng bản sao mô phỏng.",
    "what_if",
  );
  console.log(JSON.stringify({
    browser: browser.version(), provider: "scripted fixture", residentWhy,
    residentWhatIf, residentCompound, operatorCompound, operatorWhatIf,
  }, null, 2));
}

try {
  if (process.argv.includes("--ranked")) await rankedOptions();
  else await twoRoles();
} finally {
  await browser.close();
}
