import { describe, expect, it, vi, afterEach } from "vitest";
import { request } from "../services/http";
afterEach(() => vi.unstubAllGlobals());
describe("API errors and authentication", () => {
  it("forwards bearer token, cookies and JSON without altering the body", async () => {
    sessionStorage.setItem("nutriguide.token", "test-token");
    const fetch = vi.fn().mockResolvedValue(
      new Response('{"id":1}', {
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    expect(
      await request("/test", { method: "POST", body: '{"a":1}' }, "/api"),
    ).toEqual({ id: 1 });
    expect(fetch).toHaveBeenCalledWith(
      "/api/test",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        }),
      }),
    );
  });
  it("does not disguise a backend failure as demo success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('{"detail":"Không có nghiệm"}', {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    await expect(request("/meal-plans/generate")).rejects.toThrow(
      "Không có nghiệm",
    );
  });
  it("detects an HTML SPA response from a wrong API address", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html></html>", {
          headers: { "content-type": "text/html" },
        }),
      ),
    );
    await expect(request("/workspace")).rejects.toThrow("không đúng định dạng");
  });
  it("expires the client session on HTTP 401", async () => {
    const listener = vi.fn();
    window.addEventListener("nutriguide:unauthorized", listener, {
      once: true,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    await expect(request("/workspace")).rejects.toThrow();
    expect(listener).toHaveBeenCalledOnce();
  });
});
