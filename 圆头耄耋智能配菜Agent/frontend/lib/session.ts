import { SessionV2Schema } from "./contracts";
import type { SessionV2 } from "./types";

export const SESSION_STORAGE_KEY = "maodie-session-v2";

export type StorageLike = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;

export type SessionSaveResult =
  | { ok: true }
  | { ok: false; reason: "invalid-session" | "storage-unavailable" };

function defaultStorage(): StorageLike | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function parseUnknown(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

export function parseSession(raw: unknown): SessionV2 | null {
  const parsed = SessionV2Schema.safeParse(parseUnknown(raw));
  return parsed.success ? (parsed.data as unknown as SessionV2) : null;
}

export function loadSession(storage?: StorageLike): SessionV2 | null {
  const target = storage ?? defaultStorage();
  if (target === null) return null;

  let raw: string | null;
  try {
    raw = target.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;

  const session = parseSession(raw);
  if (session === null) {
    try {
      target.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // A blocked storage implementation is equivalent to no persisted session.
    }
    return null;
  }

  return session;
}

export function saveSession(
  session: SessionV2,
  storage?: StorageLike,
): SessionSaveResult {
  const parsed = SessionV2Schema.safeParse(session);
  if (!parsed.success) {
    return { ok: false, reason: "invalid-session" };
  }

  const target = storage ?? defaultStorage();
  if (target === null) {
    return { ok: false, reason: "storage-unavailable" };
  }

  try {
    target.setItem(SESSION_STORAGE_KEY, JSON.stringify(parsed.data));
    return { ok: true };
  } catch {
    return { ok: false, reason: "storage-unavailable" };
  }
}

export function clearSession(storage?: StorageLike): void {
  const target = storage ?? defaultStorage();
  if (target === null) return;
  try {
    target.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Clearing unavailable storage is already the desired observable state.
  }
}
