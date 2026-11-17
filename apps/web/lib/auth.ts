import { cookies } from "next/headers";

import { fetchCurrentUser, type SessionUser } from "@/lib/api";

/** Server-only helper: resolve the current session from the request cookies. */
export async function getCurrentUser(): Promise<SessionUser | null> {
  const cookie = (await cookies()).toString();
  if (!cookie) {
    return null;
  }
  return fetchCurrentUser(cookie);
}

export async function getRequestCookie(): Promise<string> {
  return (await cookies()).toString();
}
