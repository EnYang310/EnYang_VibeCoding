import { afterEach, describe, expect, test, vi } from "vitest";

import "./setup";
import { compressImage } from "../lib/image";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Safari-compatible image compression", () => {
  test("rejects a zero-byte image before attempting to decode it", async () => {
    const decode = vi.fn();
    vi.stubGlobal("createImageBitmap", decode);
    const file = new File([], "empty.jpg", { type: "image/jpeg" });

    await expect(compressImage(file)).rejects.toThrow("图片是空的");
    expect(decode).not.toHaveBeenCalled();
  });

  test.each(["unavailable", "throws"] as const)(
    "falls back to an HTML image when createImageBitmap is %s",
    async (bitmapBehavior) => {
      if (bitmapBehavior === "unavailable") {
        vi.stubGlobal("createImageBitmap", undefined);
      } else {
        vi.stubGlobal(
          "createImageBitmap",
          vi.fn().mockRejectedValue(new Error("Safari decode failed")),
        );
      }

      const revokeObjectURL = vi.fn();
      vi.stubGlobal("URL", {
        createObjectURL: vi.fn(() => "blob:safari-photo"),
        revokeObjectURL,
      });

      class FakeImage {
        naturalWidth = 3200;
        naturalHeight = 800;
        width = 3200;
        height = 800;
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;

        set src(_value: string) {
          queueMicrotask(() => this.onload?.());
        }
      }
      vi.stubGlobal("Image", FakeImage);

      const drawImage = vi.fn();
      const canvas = document.createElement("canvas");
      vi.spyOn(canvas, "getContext").mockReturnValue({
        drawImage,
      } as unknown as CanvasRenderingContext2D);
      vi.spyOn(canvas, "toDataURL").mockReturnValue(
        "data:image/jpeg;base64,compressed",
      );
      const createElement = document.createElement.bind(document);
      vi.spyOn(document, "createElement").mockImplementation((tagName) =>
        tagName === "canvas" ? canvas : createElement(tagName),
      );

      const file = new File(["photo"], "safari.jpg", {
        type: "image/jpeg",
      });
      await expect(compressImage(file)).resolves.toBe(
        "data:image/jpeg;base64,compressed",
      );

      expect(canvas.width).toBe(1600);
      expect(canvas.height).toBe(400);
      expect(drawImage).toHaveBeenCalledTimes(1);
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:safari-photo");
    },
  );
});
