"use client";

import React, { useCallback, useState } from "react";
import { UploadCloud, FileText, Loader2, X } from "lucide-react";

interface OcrResult {
  text: string;
  confidence: number;
  metadata: {
    word_count: number;
  };
}

interface OcrUploadDropzoneProps {
  onExtract: (result: OcrResult) => void;
  className?: string;
}

export function OcrUploadDropzone({ onExtract, className = "" }: OcrUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    <div className={`relative ${className}`}>
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
            <p className="text-sm font-medium">Processing Image...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center text-gray-400">
            <UploadCloud className="w-10 h-10 mb-4 text-gray-500" />
            <p className="text-sm font-medium mb-1 text-gray-300">
              Drag & Drop to Extract Text
            </p>
            <p className="text-xs">or click to browse files</p>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-3 flex items-center p-3 text-sm text-red-400 bg-red-400/10 rounded-md border border-red-500/20">
          <FileText className="w-4 h-4 mr-2 flex-shrink-0" />
          <span className="flex-grow">{error}</span>
          <button onClick={() => setError(null)} className="ml-2 hover:text-red-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
