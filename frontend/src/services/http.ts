export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  base = import.meta.env.VITE_API_BASE_URL || "/api",
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    path.includes("chat") ? 90000 : 30000,
  );
  const token = sessionStorage.getItem("nutriguide.token");
  try {
    const response = await fetch(base.replace(/\/$/, "") + path, {
      ...options,
      credentials: "include",
      signal: options.signal || controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (response.status === 401)
        window.dispatchEvent(new Event("nutriguide:unauthorized"));
      throw new ApiError(
        typeof body.detail === "string"
          ? body.detail
          : body.detail?.message ||
              body.message ||
              `Yêu cầu thất bại (${response.status}). Vui lòng thử lại.`,
        response.status,
        body,
      );
    }
    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json"))
      throw new ApiError(
        "Máy chủ trả dữ liệu không đúng định dạng. Kiểm tra địa chỉ API.",
        response.status,
      );
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError("Máy chủ phản hồi quá lâu. Vui lòng thử lại.", 408);
    throw new ApiError(
      "Không kết nối được máy chủ. Vui lòng kiểm tra kết nối và cấu hình API.",
      0,
    );
  } finally {
    clearTimeout(timer);
  }
}
export const json = (data: unknown) => JSON.stringify(data);
