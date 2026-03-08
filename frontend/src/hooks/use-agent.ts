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

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const connect = useCallback((sid?: string) => {
    const id = sid || crypto.randomUUID();
    const url = `${WS_URL}/${id}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setSessionId(id);
    };

    ws.onmessage = (event) => {
      const data: WSMessage = JSON.parse(event.data);

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
            const p = { ...data.profile, confidence_score: data.confidence || data.profile.confidence_score || 0 };
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
      setIsSearching(false);
    };

    ws.onerror = () => {
      setIsConnected(false);
      setIsSearching(false);
    };

    return id;
  }, [addMessage]);

  const sendQuery = useCallback((query: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      const newId = connect();
      setTimeout(() => {
        wsRef.current?.send(JSON.stringify({ type: "query", text: query }));
      }, 500);
      return;
    }

    setIsSearching(true);
    setProfile(null);
    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date(),
    });
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
        const p = { ...data.profile, confidence_score: data.confidence_score || data.profile.confidence_score || 0 };
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
