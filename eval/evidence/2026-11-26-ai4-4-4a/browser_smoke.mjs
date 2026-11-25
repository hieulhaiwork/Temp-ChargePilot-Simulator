// Run with the fixture-backed API and the built frontend listening on loopback.
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const toolkit = process.argv[2];
assert.ok(toolkit, "Pass the directory containing the temporary Playwright installation.");
const { chromium } = await import(pathToFileURL(resolve(toolkit, "node_modules/playwright/index.mjs")).href);
const base = process.argv[3] ?? "http://localhost:3000";
const browser = await chromium.launch({ headless: true });

async function login(role, email) {
  const page = await browser.newPage();
  await page.goto(`${base}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill("fixture-only-passphrase");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL(`**/${role}`);
  return { page, panel: page.getByRole("region", { name: "Copilot trạm sạc" }) };
}

async function ask(page, panel, question) {
  await panel.getByLabel("Câu hỏi").fill(question);
  const received = page.waitForResponse((response) => response.url().endsWith("/api/v1/copilot/query"));
  await panel.getByRole("button", { name: "Gửi câu hỏi" }).click();
  const response = await received;
  return [response.status(), await response.json()];
}

async function completedJob(page, panel, question) {
  const completed = page.waitForResponse(async (response) => {
    if (!response.url().includes("/api/v1/copilot/jobs/") || !response.ok()) return false;
    return (await response.json()).job.status === "succeeded";
  });
  const [status, submitted] = await ask(page, panel, question);
  assert.equal(status, 202);
  const result = (await (await completed).json()).job.result.result;
  assert.equal(result.applied, false);
  await panel.getByRole("region", { name: "Kết quả WHAT-IF" }).waitFor();
  return { parse_source: submitted.parse_source, result };
}

try {
  const resident = await login("resident", "res-resident-demo@g6a.example");
  const [whyStatus, why] = await ask(resident.page, resident.panel, "Tại sao xe của tôi vẫn chưa được sạc?");
  assert.equal(whyStatus, 200);
  assert.equal(why.kind, "why");
  await resident.panel.getByText(/Xe đang chờ vì vùng AC/).first().waitFor();
  const soc = await completedJob(resident.page, resident.panel, "Nếu tôi chỉ cần sạc đến 75% thay vì 90% thì sao?");
  await resident.panel.getByText("Cam kết sửa", { exact: true }).waitFor();
  assert.equal(soc.result.affected_vehicles[0].baseline_original.target_soc, 90);
  assert.equal(soc.result.affected_vehicles[0].patched_revised.target_soc, 75);
  assert.equal(await resident.panel.getByRole("button", { name: /áp dụng/i }).count(), 0);

  // Verify zero cross-account cache or reply leakage when switching resident account in the SAME tab.
  const bookingSelect = resident.panel.getByLabel("Lịch sạc");
  assert.equal(await bookingSelect.locator("option", { hasText: "resident-demo" }).count(), 1);
  const logoutBtn = resident.page.getByRole("button", { name: /đăng xuất/i });
  if ((await logoutBtn.count()) > 0) {
    await logoutBtn.first().click();
    await resident.page.waitForURL((url) => url.pathname === "/login");
  } else {
    await resident.page.evaluate(() => window.sessionStorage.clear());
    await resident.page.goto(`${base}/login`);
  }
  await resident.page.getByLabel("Email").fill("second-resident@g6a.example");
  await resident.page.getByLabel("Mật khẩu").fill("fixture-only-passphrase");
  await resident.page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await resident.page.waitForURL("**/resident");
  await resident.panel.waitFor();
  assert.equal(await resident.panel.getByRole("region", { name: "Kết quả WHAT-IF" }).count(), 0);
  assert.equal(await resident.panel.getByRole("region", { name: "Kết quả WHY" }).count(), 0);
  assert.equal(await resident.panel.getByLabel("Lịch sạc").locator("option", { hasText: "resident-demo" }).count(), 0);

  const operator = await login("operator", "operator@g6a.example");
  await operator.panel.getByLabel("Đầu nối").selectOption("DC-01-1");
  const outage = await completedJob(operator.page, operator.panel, "Nếu một cổng DC bị lỗi trong 30 phút thì sao?");
  await operator.panel.getByRole("rowheader", { name: "operator-dc-second", exact: true }).waitFor();
  assert.equal(outage.result.patch.duration_minutes, 30);
  const [howStatus, how] = await ask(operator.page, operator.panel, "Cần tăng công suất nguồn lên bao nhiêu để tất cả xe sạc đúng hạn?");
  assert.equal(howStatus, 200);
  assert.equal(how.code, "feature_not_available");
  await operator.panel.getByText(/HOW-TO hiện chưa khả dụng/).waitFor();
  assert.equal(await operator.panel.getByRole("button", { name: /áp dụng/i }).count(), 0);

  console.log(JSON.stringify({
    browser: browser.version(),
    resident_why: { status: whyStatus, result: why.result.status, evidence: why.claims.length },
    resident_soc: { original_target: 90, revised_target: 75, status: soc.result.status },
    same_tab_account_switch: { prior_booking_visible: false, prior_results_visible: false },
    operator_outage: { status: outage.result.status, connector: outage.result.patch.connector_id, minutes: 30 },
    operator_how_to: { status: howStatus, code: how.code },
    apply_button_count: 0,
  }, null, 2));
} finally {
  await browser.close();
}
