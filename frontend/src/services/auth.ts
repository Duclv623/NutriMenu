import type { User } from "../types";
import { uid } from "../utils";
import { API_MODE, backend } from "./api";
type Account = { user: User; salt: string; hash: string };
async function hashPassword(password: string, salt: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: new TextEncoder().encode(salt),
      iterations: 100000,
      hash: "SHA-256",
    },
    key,
    256,
  );
  return Array.from(new Uint8Array(bits))
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("");
}
export async function authenticate(
  name: string,
  email: string,
  password: string,
  register: boolean,
): Promise<User> {
  if (API_MODE === "api") {
    const result = register
      ? await backend.register(name, email, password)
      : await backend.login(email, password);
    if (result.accessToken)
      sessionStorage.setItem("nutriguide.token", result.accessToken);
    return result.user;
  }
  const accounts: Account[] = JSON.parse(
    localStorage.getItem("nutriguide.demo.accounts") || "[]",
  );
  const normalized = email.trim().toLowerCase();
  const existing = accounts.find((a) => a.user.email === normalized);
  if (register) {
    if (existing)
      throw new Error("Email này đã được đăng ký trên trình duyệt.");
    const salt = uid();
    const user = {
      id: uid(),
      name: name.trim(),
      email: normalized,
      demo: true,
    };
    accounts.push({ user, salt, hash: await hashPassword(password, salt) });
    localStorage.setItem("nutriguide.demo.accounts", JSON.stringify(accounts));
    return user;
  }
  if (
    !existing ||
    existing.hash !== (await hashPassword(password, existing.salt))
  )
    throw new Error("Email hoặc mật khẩu chưa đúng.");
  return existing.user;
}
export const demoUser: User = {
  id: "demo",
  name: "Minh Anh",
  email: "demo@nutriguide.local",
  demo: true,
};
