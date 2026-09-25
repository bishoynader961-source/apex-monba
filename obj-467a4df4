"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

interface Props<T> {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (val: string) => void;
  onSelect: (item: T) => void;
  onSearch: (q: string) => Promise<T[]>;
  renderItem: (item: T) => React.ReactNode;
  className?: string;
  required?: boolean;
}

export function SearchableInput<T>({
  label,
  placeholder,
  value,
  onChange,
  onSelect,
  onSearch,
  renderItem,
  className = "",
  required = false,
}: Props<T>) {
  const [results, setResults] = useState<T[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  // Stable id so the visible label is programmatically linked to the input.
  const inputId = useId();

  const search = useCallback(
    async (q: string) => {
      if (q.length < 1) {
        setResults([]);
        setOpen(false);
        return;
      }
      setLoading(true);
      try {
        const items = await onSearch(q);
        setResults(items);
        setOpen(items.length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [onSearch],
  );

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleChange = (val: string) => {
    onChange(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void search(val), 250);
  };

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <label htmlFor={inputId} className="block text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wider font-medium mb-1">
        {label} {required && <span className="text-red-400">*</span>}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder ?? `Search ${label.toLowerCase()}...`}
          className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm focus:border-blue-500 outline-none"
        />
        {loading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">...</span>
        )}
      </div>
      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-h-60 overflow-y-auto z-50">
          {results.map((item, i) => (
            <button
              key={i}
              type="button"
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-600/30 border-b border-gray-700/50 last:border-0"
              onClick={() => {
                onSelect(item);
                setOpen(false);
              }}
            >
              {renderItem(item)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
