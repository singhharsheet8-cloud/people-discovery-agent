"use client";

import { useState } from "react";
import { Copy, Check, FileText } from "lucide-react";
import type { DiscoverRequest } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface ApiDocsPanelProps {
  formValues: DiscoverRequest;
}

export function ApiDocsPanel({ formValues }: ApiDocsPanelProps) {
  const [copied, setCopied] = useState(false);

  const body = JSON.stringify(
    {
      name: formValues.name || "",
      company: formValues.company || "",
      role: formValues.role || "",
      location: formValues.location || "",
      linkedin_url: formValues.linkedin_url || "",
      twitter_handle: formValues.twitter_handle || "",
      github_username: formValues.github_username || "",
      context: formValues.context || "",
    },
    null,
    2
  );

  const curlCommand = `curl -X POST ${API_BASE}/discover \\
  -H "Content-Type: application/json" \\
  -d '${body.replace(/'/g, "'\\''")}'`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(curlCommand);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement("textarea");
      textArea.value = curlCommand;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <FileText size={18} className="text-gray-400" />
          <span className="text-sm font-medium text-gray-300">API Documentation</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white transition-colors"
        >
          {copied ? (
            <>
              <Check size={14} className="text-emerald-400" />
              Copied
            </>
          ) : (
            <>
              <Copy size={14} />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-xs text-gray-400 font-mono leading-relaxed">
        <code>{curlCommand}</code>
      </pre>
    </div>
  );
}
