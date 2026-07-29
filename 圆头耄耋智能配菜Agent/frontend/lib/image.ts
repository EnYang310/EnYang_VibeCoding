type DecodedImage = {
  source: CanvasImageSource;
  width: number;
  height: number;
  dispose: () => void;
};

function decodeWithHtmlImage(file: File): Promise<DecodedImage> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    const dispose = () => URL.revokeObjectURL(objectUrl);

    image.onload = () => {
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      if (width <= 0 || height <= 0) {
        dispose();
        reject(new Error("浏览器无法读取这张图片"));
        return;
      }
      resolve({ source: image, width, height, dispose });
    };
    image.onerror = () => {
      dispose();
      reject(new Error("浏览器无法读取这张图片"));
    };
    image.src = objectUrl;
  });
}

async function decodeImage(file: File): Promise<DecodedImage> {
  if (typeof globalThis.createImageBitmap === "function") {
    try {
      const bitmap = await globalThis.createImageBitmap(file);
      if (bitmap.width > 0 && bitmap.height > 0) {
        return {
          source: bitmap,
          width: bitmap.width,
          height: bitmap.height,
          dispose: () => bitmap.close(),
        };
      }
      bitmap.close();
    } catch {
      // Safari can expose createImageBitmap but reject otherwise valid photos.
    }
  }
  return decodeWithHtmlImage(file);
}

export async function compressImage(file: File): Promise<string> {
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    throw new Error("请上传 JPG、PNG 或 WebP 图片");
  }
  if (file.size === 0) {
    throw new Error("图片是空的，请重新选择");
  }
  if (file.size > 20 * 1024 * 1024) {
    throw new Error("图片太大了，请选择 20MB 以内的照片");
  }

  const decoded = await decodeImage(file);
  const maxEdge = 1600;
  const scale = Math.min(
    1,
    maxEdge / Math.max(decoded.width, decoded.height),
  );
  const width = Math.max(1, Math.round(decoded.width * scale));
  const height = Math.max(1, Math.round(decoded.height * scale));
  try {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("浏览器无法处理这张图片");
    context.drawImage(decoded.source, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.82);
  } finally {
    decoded.dispose();
  }
}
