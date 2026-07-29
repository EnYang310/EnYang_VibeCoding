import { describe, expect, test, vi } from "vitest";

import "./setup";
import {
  SESSION_STORAGE_KEY,
  loadSession,
  parseSession,
  saveSession,
} from "../lib/session";
import {
  cloneFixture,
  swappingSession,
  validSessionV2,
} from "./fixtures";

function memoryStorage(initial?: Record<string, string>) {
  const values = new Map(Object.entries(initial ?? {}));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    removeItem: vi.fn((key: string) => values.delete(key)),
  };
}

describe("session v2", () => {
  test("atomically saves and restores an active swap", () => {
    const storage = memoryStorage();
    const session = swappingSession();

    expect(saveSession(session, storage)).toEqual({ ok: true });
    expect(loadSession(storage)).toEqual(session);
    expect(storage.setItem).toHaveBeenCalledWith(
      SESSION_STORAGE_KEY,
      JSON.stringify(session),
    );
  });

  test("rejects v1 and dirty sessions", () => {
    const old = { ...cloneFixture(validSessionV2), version: 1 };
    expect(parseSession(old)).toBeNull();
    expect(parseSession("{")).toBeNull();
  });

  test("rejects an active swap for another plan or channel", () => {
    const wrongPlan = swappingSession();
    wrongPlan.activeSwap!.planId = "other";
    expect(parseSession(wrongPlan)).toBeNull();

    const wrongChannel = swappingSession();
    wrongChannel.activeSwap!.channelId = "missing";
    expect(parseSession(wrongChannel)).toBeNull();
  });

  test("removes invalid persisted data", () => {
    const storage = memoryStorage({
      [SESSION_STORAGE_KEY]: JSON.stringify({
        ...validSessionV2,
        version: 1,
      }),
    });
    expect(loadSession(storage)).toBeNull();
    expect(storage.removeItem).toHaveBeenCalledWith(SESSION_STORAGE_KEY);
  });
});
