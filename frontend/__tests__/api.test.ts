import { api, ApiError, refreshSession, session } from "@/src/api";

type R = { status: number; body?: unknown };
const res = ({ status, body }: R) => ({ ok: status < 400, status, text: async () => (body === undefined ? "" : JSON.stringify(body)), json: async () => body });

describe("API client: errors, refresh, session expiry, suspension", () => {
  let calls: { url: string; init: any }[];
  let queue: R[];
  beforeEach(() => {
    calls = [];
    queue = [];
    (global as any).fetch = jest.fn(async (url: string, init: any) => {
      calls.push({ url, init });
      const next = queue.shift();
      if (!next) throw new TypeError("Network request failed");
      return res(next);
    });
    session.setToken("access-1");
    session.setRefreshToken("refresh-1");
    session.setSchool("school-A");
  });

  it("sends bearer token and tenant header", async () => {
    queue.push({ status: 200, body: { ok: true } });
    await api("/school");
    expect(calls[0].init.headers.Authorization).toBe("Bearer access-1");
    expect(calls[0].init.headers["X-School-Id"]).toBe("school-A");
  });

  it("formats FastAPI validation errors into readable messages", async () => {
    queue.push({ status: 422, body: { detail: [{ loc: ["body", "first_name"], msg: "Value error, too short" }] } });
    await expect(api("/students", { body: {} })).rejects.toMatchObject({ status: 422, message: "first name: too short" });
  });

  it("maps network failures to an offline message", async () => {
    await expect(api("/school")).rejects.toThrow(/offline/);
  });

  it("refreshes an expired access token once and retries", async () => {
    const saved: string[] = [];
    session.onTokens((a, r) => saved.push(a, r));
    queue.push({ status: 401, body: { detail: "Access token expired" } }, { status: 200, body: { access_token: "access-2", refresh_token: "refresh-2" } }, { status: 200, body: { ok: 1 } });
    await expect(api("/school")).resolves.toEqual({ ok: 1 });
    expect(calls[1].url).toMatch(/\/auth\/refresh$/);
    expect(JSON.parse(calls[1].init.body)).toEqual({ refresh_token: "refresh-1" });
    expect(calls[2].init.headers.Authorization).toBe("Bearer access-2");
    expect(saved).toEqual(["access-2", "refresh-2"]);
  });

  it("signs out when refresh fails (session expired / revoked)", async () => {
    const out = jest.fn();
    session.onUnauthorized(out);
    queue.push({ status: 401, body: { detail: "Session revoked" } }, { status: 401, body: { detail: "Refresh token reuse detected" } });
    await expect(api("/school")).rejects.toBeInstanceOf(ApiError);
    expect(out).toHaveBeenCalledTimes(1);
  });

  it("does not try to refresh failed logins", async () => {
    queue.push({ status: 401, body: { detail: "Incorrect email or password" } });
    await expect(api("/auth/login", { body: {} })).rejects.toThrow("Incorrect email or password");
    expect(calls).toHaveLength(1);
  });

  it("shares one refresh between concurrent callers (no false reuse)", async () => {
    let resolve: (v: any) => void = () => {};
    (global as any).fetch = jest.fn(() => new Promise((r) => (resolve = r)));
    const a = refreshSession();
    const b = refreshSession();
    resolve(res({ status: 200, body: { access_token: "x", refresh_token: "y" } }));
    await expect(Promise.all([a, b])).resolves.toEqual([true, true]);
    expect((global as any).fetch).toHaveBeenCalledTimes(1);
  });

  it("notifies the app when the school is suspended", async () => {
    const inactive = jest.fn();
    session.onSchoolInactive(inactive);
    queue.push({ status: 403, body: { detail: "This school account is not active" } });
    await expect(api("/school")).rejects.toMatchObject({ status: 403 });
    expect(inactive).toHaveBeenCalled();
  });
});
