"use client";

import { useState, useEffect, useRef } from "react";

interface Suggestion {
  id?: string;
  name?: string;
  company?: string;
}

interface AutoSuggestProps {
  type: "person" | "company";
  value: string;
  onChange: (value: string) => void;
  onSelect?: (suggestion: Suggestion) => void;
  placeholder?: string;
  className?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export function AutoSuggest({
  type,
  value,
  onChange,
  onSelect,
  placeholder,
  className,
}: AutoSuggestProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    if (!value || value.length < 2) {
      setSuggestions([]);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(
          `${API_BASE}/suggest?q=${encodeURIComponent(value)}&type=${type}`
        );
        const data = await res.json();
        setSuggestions(data);
        setOpen(data.length > 0);
      } catch {
        setSuggestions([]);
      }
    }, 300);
  }, [value, type]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={
          className ||
          "w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        }
        onFocus={() => suggestions.length > 0 && setOpen(true)}
      />
      {open && suggestions.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1a1a] border border-white/10 rounded-lg shadow-xl overflow-hidden">
          {suggestions.map((s, i) => (
            <button
              key={s.id ?? i}
              type="button"
              className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 transition-colors"
              onClick={() => {
                onChange(s.name || s.company || "");
                onSelect?.(s);
                setOpen(false);
              }}
            >
              {type === "person" ? (
                <span>
                  {s.name}{" "}
                  {s.company && (
                    <span className="text-gray-500">— {s.company}</span>
                  )}
                </span>
              ) : (
                <span>{s.company}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
