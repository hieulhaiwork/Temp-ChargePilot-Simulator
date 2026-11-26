import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

it("handles delayed 401 against the requesting generation, even for the same account", async () => {
  vi.resetModules();
  const responses: ((response: Response) => void)[] = [];
  const fetch = vi.fn((request: Request) => new Promise<Response>((resolve) => {
    expect(request.headers.get("Authorization")).toBe("Bearer deterministic-fixture");
    responses.push(resolve);
  }));
  vi.stubGlobal("fetch", fetch);
  const { clearSession, getSession, setSession } = await import("@/lib/auth/session");
  const { api, unwrap } = await import("@/lib/api/client");
  const credentials = { token: "deterministic-fixture", role: "resident" as const, userId: "resident", displayName: "Fixture" };
  const request = () => unwrap(api.GET("/api/v1/copilot/context")).catch((error: unknown) => error);
  const unauthorized = () => new Response(JSON.stringify({ detail: "Expired" }), {
    status: 401, headers: { "Content-Type": "application/json" },
  });
  setSession(credentials);
  const fromOldLogin = request();
  await vi.waitFor(() => expect(responses).toHaveLength(1));
  const generation = getSession()?.generation;
  clearSession();
  setSession(credentials);
  const current = getSession()?.generation;
  responses[0](unauthorized());
  expect(await fromOldLogin).toMatchObject({ status: 401 });
  expect(getSession()).toMatchObject(credentials);
  expect(getSession()?.generation).toBe(current);
  expect(current).not.toBe(generation);
  const fromCurrentLogin = request();
  await vi.waitFor(() => expect(responses).toHaveLength(2));
  responses[1](unauthorized());
  expect(await fromCurrentLogin).toMatchObject({ status: 401 });
  expect(getSession()).toBeNull();
});
