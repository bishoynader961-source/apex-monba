"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, AlertCircle, CheckCircle, Info, Stethoscope } from "lucide-react";
import { parseSigCode } from "@/lib/api/dictionaries";
import type { SigCodeParseResult } from "@/types/contracts";

interface SigCodeInputProps {
  value: string;
  onChange: (value: string) => void;
  onParsed?: (result: SigCodeParseResult) => void;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
  autoFocus?: boolean;
}

export function SigCodeInput({
  value,
  onChange,
  onParsed,
  disabled = false,
  className = "",
  placeholder = "Enter SIG code (e.g., 1TAB BID x10D)",
  autoFocus = false,
}: SigCodeInputProps) {
  const [localValue, setLocalValue] = useState(value);
  const [parsed, setParsed] = useState<SigCodeParseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync with external value changes
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  // Auto-focus on mount
  useEffect(() => {
    if (autoFocus && inputRef.current) {
      inputRef.current.focus();
    }
  }, [autoFocus]);

  const parseSig = useCallback(async (code: string) => {
    if (!code.trim() || code.length < 2) {
      setParsed(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await parseSigCode(code);
      setParsed(result);
      onParsed?.(result);

      if (!result.matched) {
        setError("SIG code not recognized");
      }
    } catch {
      setError("Failed to parse SIG code");
    } finally {
      setLoading(false);
    }
  }, [onParsed]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    onChange(newValue);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      parseSig(newValue);
    }, 300);
  };

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const getStatusIcon = () => {
    if (loading) return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
    if (error) return <AlertCircle className="w-4 h-4 text-red-500" />;
    if (parsed?.matched) return <CheckCircle className="w-4 h-4 text-green-500" />;
    if (parsed && !parsed.matched) return <Info className="w-4 h-4 text-amber-500" />;
    return null;
  };

  const getStatusText = () => {
    if (loading) return "Parsing…";
    if (error) return error;
    if (parsed?.matched) return "Valid SIG code";
    if (parsed && !parsed.matched) return "Code not recognized";
    return "Enter SIG code";
  };

  const getStatusClass = () => {
    if (loading) return "text-blue-500";
    if (error) return "text-red-500";
    if (parsed?.matched) return "text-green-600";
    if (parsed && !parsed.matched) return "text-amber-600";
    return "text-slate-400";
  };

  const getParsedDetails = () => {
    if (!parsed?.matched || !parsed.full_text) return null;

    const details: string[] = [];
    if (parsed.detail) details.push(parsed.detail);
    if (parsed.full_text) details.push(`→ ${parsed.full_text}`);
    return details.join(" ");
  };

  return (
    <div className={`relative w-full ${className}`}>
      <label htmlFor="sig-code-input" className="block text-xs font-medium text-slate-500 mb-1">
        SIG Code
      </label>
      <div className="relative">
        <input
          id="sig-code-input"
          ref={inputRef}
          type="text"
          value={localValue}
          onChange={handleChange}
          disabled={disabled}
          placeholder={placeholder}
          className={`w-full pl-10 pr-10 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-slate-900 placeholder:text-slate-400 disabled:bg-slate-100 disabled:text-slate-500 transition-all ${loading ? "pr-10" : ""}`}
          aria-label="SIG code input"
        />
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Stethoscope className="w-4 h-4 text-gray-600 dark:text-slate-400" />
        </div>
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
          {getStatusIcon()}
        </div>
      </div>

      {/* Status message */}
      <p className={`mt-1.5 text-xs transition-colors ${getStatusClass()}`}>
        {getStatusText()}
      </p>

      {/* Parsed details */}
      {getParsedDetails() && (
        <p className="mt-1.5 text-xs text-slate-500 bg-slate-50 rounded-md p-2 font-mono text-xs">
          {getParsedDetails()}
        </p>
      )}

      {/* Auto-fill hint */}
      {parsed?.matched && (
        <p className="mt-1.5 text-xs text-emerald-600">
          ✓ Parsed successfully — Quantity and Days Supply will be auto-filled
        </p>
      )}
    </div>
  );
}

// Need to import Stethoscope
export default SigCodeInput;