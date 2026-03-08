"use client";

import { useState, useRef, useEffect } from "react";
import { Send, RotateCcw, User, Bot, Loader2, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/types";

interface ChatInterfaceProps {
  messages: ChatMessage[];
  isSearching: boolean;
  onSendQuery: (query: string) => void;
  onSendClarification: (response: string) => void;
  onReset: () => void;
}

export function ChatInterface({
  messages,
  isSearching,
  onSendQuery,
  onSendClarification,
  onReset,
}: ChatInterfaceProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const hasStarted = messages.length > 0;

  const lastClarification = [...messages].reverse().find(
    (m) => m.data?.type === "clarification"
  );
  const needsClarification = lastClarification && !messages.some(
    (m) => m.role === "user" && m.timestamp > lastClarification.timestamp
  );

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSearching) return;

    if (needsClarification) {
      onSendClarification(input.trim());
    } else {
      onSendQuery(input.trim());
    }
    setInput("");
  };

  const handleSuggestionClick = (suggestion: string) => {
    if (isSearching) return;
    onSendClarification(suggestion);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {!hasStarted && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center mb-4">
              <User size={28} className="text-white" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">People Discovery Agent</h2>
            <p className="text-gray-400 text-sm max-w-md mb-6">
              Tell me about someone you want to find. I&apos;ll search across LinkedIn, YouTube,
              news articles, and the web to build a comprehensive profile.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {[
                "Find Andrej Karpathy",
                "Who is the CEO of Anthropic?",
                "Find John from Google DeepMind who works on LLMs",
              ].map((example) => (
                <button
                  key={example}
                  onClick={() => { setInput(example); inputRef.current?.focus(); }}
                  className="px-3 py-1.5 rounded-lg text-xs text-gray-400 glass glass-hover"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onSuggestionClick={handleSuggestionClick}
            isSearching={isSearching}
          />
        ))}

        {isSearching && (
          <div className="flex items-center gap-2 text-gray-500 text-sm pl-10">
            <Loader2 size={14} className="animate-spin" />
            <span>Searching...</span>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-white/10 p-4">
        <form onSubmit={handleSubmit} className="flex items-center gap-3">
          {hasStarted && (
            <button
              type="button"
              onClick={onReset}
              className="p-2 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors"
              title="New search"
            >
              <RotateCcw size={18} />
            </button>
          )}
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                needsClarification
                  ? "Answer the question above..."
                  : hasStarted
                    ? "Search for another person..."
                    : "Describe the person you want to find..."
              }
              disabled={isSearching}
              className={cn(
                "w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10",
                "text-sm text-white placeholder:text-gray-500",
                "focus:outline-none focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/25",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "transition-all duration-200",
              )}
            />
          </div>
          <button
            type="submit"
            disabled={!input.trim() || isSearching}
            className={cn(
              "p-3 rounded-xl transition-all duration-200",
              input.trim() && !isSearching
                ? "bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/25"
                : "bg-white/5 text-gray-600 cursor-not-allowed",
            )}
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onSuggestionClick,
  isSearching,
}: {
  message: ChatMessage;
  onSuggestionClick: (s: string) => void;
  isSearching: boolean;
}) {
  if (message.role === "system") {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-500 pl-10 animate-fade-in">
        <Info size={12} />
        <span>{message.content}</span>
      </div>
    );
  }

  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3 animate-slide-up", isUser && "flex-row-reverse")}>
      <div className={cn(
        "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5",
        isUser
          ? "bg-brand-600 text-white"
          : "bg-gradient-to-br from-purple-600 to-brand-600 text-white",
      )}>
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div className={cn("max-w-[80%] space-y-2", isUser && "items-end")}>
        <div className={cn(
          "rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-brand-600 text-white rounded-tr-md"
            : "glass text-gray-200 rounded-tl-md",
        )}>
          {message.content}
        </div>

        {/* Suggestion chips for clarification */}
        {message.data?.type === "clarification" && message.data.suggestions && message.data.suggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.data.suggestions.map((suggestion, idx) => (
              <button
                key={`${suggestion}-${idx}`}
                onClick={() => onSuggestionClick(suggestion)}
                disabled={isSearching}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium transition-all",
                  "bg-brand-500/10 text-brand-300 border border-brand-500/20",
                  "hover:bg-brand-500/20 hover:border-brand-500/30",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
