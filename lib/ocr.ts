// tesseract.js (~2 MB with its worker glue) is only needed when the user
// actually runs OCR on an invoice image; import it lazily so it never lands
// in the main bundle (Phase 3 diagnostics: performance / lazy loading).
export interface OcrResult {
  text: string;
  confidence: number;
}

export async function recognizeText(
  imageFile: File | Blob,
  onProgress?: (progress: number) => void,
): Promise<OcrResult> {
  const { default: Tesseract } = await import("tesseract.js");
  const result = await Tesseract.recognize(imageFile, "eng", {
    logger: (m) => {
      if (m.status === "recognizing text" && onProgress) {
        onProgress(Math.round((m.progress ?? 0) * 100));
      }
    },
  });

  return {
    text: result.data.text,
    confidence: result.data.confidence,
  };
}
