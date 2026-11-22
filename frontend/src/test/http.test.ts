import { describe, expect, it, vi, afterEach } from "vitest";
import { ApiError, request } from "../services/http";
import { rag } from "../services/api";
afterEach(() => vi.unstubAllGlobals());
describe("API errors and authentication", () => {
  it("forwards cancellation and unlocks a pending request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            options.signal!.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      ),
    );
    const controller = new AbortController();
    const pending = request("/chat", { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toThrow("Đã dừng chờ");
  });
  it("preserves Retry-After without pretending a rate limit is a lost session", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"Quá nhiều câu hỏi"}', {
            status: 429,
            headers: { "retry-after": "12" },
          }),
        ),
    );
    try {
      await request("/chat");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).retryAfter).toBe(12);
      expect((error as ApiError).status).toBe(429);
    }
  });
  it("preserves the camelCase meal-context JSON returned by FastAPI", async () => {
    const snapshot = {
      dataMode: "http",
      plan: { id: "8", date: "2026-11-21" },
      profile: {},
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(snapshot), {
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    expect((await rag.context("8")).dataMode).toBe("http");
  });
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
