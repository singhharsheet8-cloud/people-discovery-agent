"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { ChatMessage, PersonProfile, WSMessage } from "@/lib/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/ws";

export function useAgent() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [profile, setProfile] = useState<PersonProfile | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingQueryRef = useRef<string | null>(null);
  const intentionalCloseRef = useRef(false);

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const connect = useCallback((sid?: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return sessionId || sid || "";
    }

    const id = sid || crypto.randomUUID();
    const url = `${WS_URL}/${id}`;

    intentionalCloseRef.current = false;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setSessionId(id);

      if (pendingQueryRef.current) {
        const q = pendingQueryRef.current;
        pendingQueryRef.current = null;
        setIsSearching(true);
        ws.send(JSON.stringify({ type: "query", text: q }));
      }
    };

    ws.onmessage = (event) => {
      let data: WSMessage;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.type) {
        case "connected":
          setSessionId(data.session_id || id);
          break;

        case "status":
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: data.message || data.step || "Processing...",
            timestamp: new Date(),
            data: { type: "status" },
          });
          break;

        case "clarification":
          setIsSearching(false);
          addMessage({
            id: crypto.randomUUID(),
            role: "agent",
            content: data.question || "Can you provide more details?",
            timestamp: new Date(),
            data: {
              type: "clarification",
              suggestions: data.suggestions || [],
            },
          });
          break;

        case "result":
          setIsSearching(false);
          if (data.profile) {
            const p: PersonProfile = {
              name: data.profile.name || "Unknown",
              confidence_score: data.confidence || data.profile.confidence_score || 0,
              current_role: data.profile.current_role,
              company: data.profile.company,
              location: data.profile.location,
              bio: data.profile.bio,
              linkedin_url: data.profile.linkedin_url,
              key_facts: data.profile.key_facts || [],
              education: data.profile.education || [],
              expertise: data.profile.expertise || [],
              notable_work: data.profile.notable_work || [],
              social_links: data.profile.social_links || {},
              sources: (data.profile.sources || []).map((s) => ({
                title: s.title || "",
                url: s.url || "",
                platform: s.platform || "web",
                snippet: s.snippet || "",
                relevance_score: s.relevance_score ?? 0.5,
              })),
            };
            setProfile(p);
            addMessage({
              id: crypto.randomUUID(),
              role: "agent",
              content: `Found profile for ${p.name} with ${Math.round(p.confidence_score * 100)}% confidence.`,
              timestamp: new Date(),
              data: { type: "result", profile: p, confidence: p.confidence_score },
            });
          }
          break;

        case "error":
          setIsSearching(false);
          addMessage({
            id: crypto.randomUUID(),
            role: "system",
            content: `Error: ${data.message}`,
            timestamp: new Date(),
          });
          break;
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      if (!intentionalCloseRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          connect(id);
        }, 3000);
      }
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    return id;
  }, [addMessage, sessionId]);

  const sendQuery = useCallback((query: string) => {
    setIsSearching(true);
    setProfile(null);
    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date(),
    });

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      pendingQueryRef.current = query;
      connect();
      return;
    }

    wsRef.current.send(JSON.stringify({ type: "query", text: query }));
  }, [connect, addMessage]);

  const sendClarification = useCallback((response: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setIsSearching(true);
    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: response,
      timestamp: new Date(),
    });
    wsRef.current.send(JSON.stringify({ type: "clarification_response", text: response }));
  }, [addMessage]);

  const loadSession = useCallback(async (sid: string) => {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
    try {
      const res = await fetch(`${API_URL}/sessions/${sid}`);
      if (!res.ok) return;
      const data = await res.json();

      intentionalCloseRef.current = true;
      wsRef.current?.close();
      wsRef.current = null;
      setMessages([]);
      setIsSearching(false);
      setIsConnected(false);
      setSessionId(sid);

      if (data.query) {
        setMessages([{
          id: crypto.randomUUID(),
          role: "user" as const,
          content: data.query,
          timestamp: new Date(data.created_at || Date.now()),
        }]);
      }

      if (data.profile) {
        const p: PersonProfile = {
          name: data.profile.name || "Unknown",
          confidence_score: data.confidence_score || data.profile.confidence_score || 0,
          current_role: data.profile.current_role,
          company: data.profile.company,
          location: data.profile.location,
          bio: data.profile.bio,
          linkedin_url: data.profile.linkedin_url,
          key_facts: data.profile.key_facts || [],
          education: data.profile.education || [],
          expertise: data.profile.expertise || [],
          notable_work: data.profile.notable_work || [],
          social_links: data.profile.social_links || {},
          sources: (data.profile.sources || []).map((s: Record<string, unknown>) => ({
            title: (s.title as string) || "",
            url: (s.url as string) || "",
            platform: (s.platform as string) || "web",
            snippet: (s.snippet as string) || "",
            relevance_score: (s.relevance_score as number) ?? 0.5,
          })),
        };
        setProfile(p);
        setMessages((prev) => [...prev, {
          id: crypto.randomUUID(),
          role: "agent" as const,
          content: `Found profile for ${p.name} with ${Math.round(p.confidence_score * 100)}% confidence.`,
          timestamp: new Date(),
          data: { type: "result" as const, profile: p, confidence: p.confidence_score },
        }]);
      } else {
        setProfile(null);
      }
    } catch {
      // API unavailable
    }
  }, []);

  const reset = useCallback(() => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    setMessages([]);
    setProfile(null);
    setIsSearching(false);
    setIsConnected(false);
    setSessionId(null);
  }, []);

  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, []);

  return {
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
  };
}
