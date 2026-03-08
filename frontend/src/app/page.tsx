"use client";

import { useEffect, useState } from "react";
import { useAgent } from "@/hooks/use-agent";
import { ChatInterface } from "@/components/chat-interface";
import { PersonProfile } from "@/components/person-profile";
import { SearchProgress } from "@/components/search-progress";
import { SessionHistory } from "@/components/session-history";
import { Zap, PanelLeftClose, PanelLeft } from "lucide-react";

export default function Home() {
  const {
    messages,
    profile,
    isConnected,
    isSearching,
    sessionId,
    connect,
    sendQuery,
    sendClarification,
    loadSession,
    reset,
  } = useAgent();

  const [showHistory, setShowHistory] = useState(true);

  useEffect(() => {
    connect();
  }, [connect]);

  const stepKey = (() => {
    const statusMsgs = messages.filter((m) => m.role === "system");
    const last = statusMsgs[statusMsgs.length - 1]?.content || "";
    if (last.includes("Planning")) return "plan_searches";
    if (last.includes("Searching")) return "execute_searches";
    if (last.includes("Cross-referencing") || last.includes("nalyz")) return "analyze_results";
    if (last.includes("confidence") || last.includes("Evaluat")) return "check_confidence";
    if (last.includes("clarification") || last.includes("pinpoint")) return "ask_clarification";
    if (last.includes("Building") || last.includes("profile")) return "synthesize_profile";
    if (last.includes("complete")) return "complete";
    return null;
  })();

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-white/10 px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors lg:hidden"
          >
            {showHistory ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
          </button>
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center">
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">People Discovery Agent</h1>
            <p className="text-[11px] text-gray-500">AI-powered person search with confidence scoring</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors hidden lg:block"
            title={showHistory ? "Hide history" : "Show history"}
          >
            {showHistory ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
          </button>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-400" : "bg-red-400"}`} />
            <span className="text-xs text-gray-500">{isConnected ? "Connected" : "Disconnected"}</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* History Sidebar */}
        {showHistory && (
          <div className="w-64 border-r border-white/10 shrink-0 hidden lg:block">
            <SessionHistory onLoadSession={loadSession} currentSessionId={sessionId} />
          </div>
        )}

        {/* Chat Panel */}
        <div className="flex-1 flex flex-col min-w-0">
          <ChatInterface
            messages={messages}
            isSearching={isSearching}
            onSendQuery={sendQuery}
            onSendClarification={sendClarification}
            onReset={reset}
          />
        </div>

        {/* Profile / Progress Side Panel */}
        {(profile || isSearching) && (
          <div className="w-[480px] border-l border-white/10 overflow-y-auto p-4 space-y-4 shrink-0 hidden xl:block">
            {isSearching && (
              <SearchProgress currentStep={stepKey} isActive={isSearching} />
            )}
            {profile && <PersonProfile profile={profile} />}
          </div>
        )}
      </div>
    </div>
  );
}
