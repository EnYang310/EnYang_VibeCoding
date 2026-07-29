import { describe, expect, test } from "vitest";

import "./setup";
import { OperationEpoch } from "../lib/operation";

describe("OperationEpoch", () => {
  test("begin aborts the previous operation", () => {
    const operations = new OperationEpoch();
    const first = operations.begin();
    const second = operations.begin();

    expect(first.signal.aborted).toBe(true);
    expect(second.signal.aborted).toBe(false);
    expect(second.epoch).toBeGreaterThan(first.epoch);
  });

  test("cancel invalidates the current epoch", () => {
    const operations = new OperationEpoch();
    const current = operations.begin();

    operations.cancel();

    expect(current.signal.aborted).toBe(true);
    expect(operations.canCommit(current)).toBe(false);
  });

  test("only the latest live operation may commit", () => {
    const operations = new OperationEpoch();
    const stale = operations.begin();
    const current = operations.begin();

    expect(operations.canCommit(stale)).toBe(false);
    expect(operations.canCommit(current)).toBe(true);
  });
});
