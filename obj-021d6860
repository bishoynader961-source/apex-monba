"use client";

import React, { useCallback, useState } from "react";
import { UploadCloud, FileText, Loader2, X, CheckCircle, AlertTriangle } from "lucide-react";

interface TierInfo {
  tier: number;
  name: string;
  confidence: number;
  passed: boolean;
  elapsed_ms: number;
}

interface OcrResult {
  text: string;
  confidence: number;
  successful_tier: number;
  successful_tier_name: string;
  needs_review: boolean;
  word_count: number;
  tiers: TierInfo[];
}

interface OcrUploadDropzoneProps {
  onExtract: (result: OcrResult) => void;
  className?: string;
}

function ConfidenceBar({ confidence, passed }: { confidence: number; passed: boolean }) {
  const pct = Math.round(confidence * 100);
  const color = passed ? "bg-green-500" : confidence >= 0.5 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-gray-600 dark:text-gray-400 w-10 text-right">{pct}%</span>
    </div>
  );
}

export function OcrUploadDropzone({ onExtract, className = "" }: OcrUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OcrResult | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragging(true);
    } else if (e.type === "dragleave") {
      setIsDragging(false);
    }
  }, []);

  const processFile = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      setError("Please upload an image file.");
      return;
    }

    setIsUploading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/v1/ocr", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to process OCR");
      }

      const data: OcrResult = await res.json();
      setResult(data);
      onExtract(data);
    } catch (err: any) {
      setError(err.message || "An error occurred during OCR extraction.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  return (
    <div className={`space-y-4 ${className}`}>
      <div
        className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center transition-colors ${
          isDragging
            ? "border-blue-500 bg-blue-500/10"
            : "border-gray-700 hover:border-gray-500 bg-[#0d0d20]"
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept="image/*"
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          onChange={handleChange}
          disabled={isUploading}
        />

        {isUploading ? (
          <div className="flex flex-col items-center text-blue-400">
            <Loader2 className="w-10 h-10 mb-4 animate-spin" />
            <p className="text-sm font-medium">Running OCR cascade...</p>
            <p className="text-xs text-gray-500 mt-1">Testing multiple extraction tiers</p>
          </div>
        ) : (
          <div className="flex flex-col items-center text-gray-600 dark:text-gray-400">
            <UploadCloud className="w-10 h-10 mb-4 text-gray-500" />
            <p className="text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
              Drag & Drop to Extract Text
            </p>
            <p className="text-xs">or click to browse files</p>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center p-3 text-sm text-red-400 bg-red-400/10 rounded-md border border-red-500/20">
          <FileText className="w-4 h-4 mr-2 flex-shrink-0" />
          <span className="flex-grow">{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-red-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {result && (
        <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">OCR Result</h4>
            <div className="flex items-center gap-2">
              {result.needs_review ? (
                <span className="flex items-center gap-1 text-xs text-amber-400">
                  <AlertTriangle className="w-3 h-3" /> Needs Review
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs text-green-400">
                  <CheckCircle className="w-3 h-3" /> Verified
                </span>
              )}
              <span className="text-xs text-gray-500">
                Tier {result.successful_tier}: {result.successful_tier_name}
              </span>
            </div>
          </div>

          <div className="text-sm text-gray-700 dark:text-gray-300 bg-[#0d0d20] rounded p-3 max-h-32 overflow-y-auto whitespace-pre-wrap">
            {result.text || "(no text extracted)"}
          </div>

          <div className="space-y-1.5">
            {result.tiers.map((tier) => (
              <div key={tier.tier} className="flex items-center gap-3 text-xs">
                <span className="w-32 text-gray-600 dark:text-gray-400 truncate">{tier.name}</span>
                <div className="flex-1">
                  <ConfidenceBar confidence={tier.confidence} passed={tier.passed} />
                </div>
                <span className="w-16 text-right text-gray-500">{tier.elapsed_ms}ms</span>
              </div>
            ))}
          </div>

          <p className="text-xs text-gray-500">
            {result.word_count} words extracted
          </p>
        </div>
      )}
    </div>
  );
}
