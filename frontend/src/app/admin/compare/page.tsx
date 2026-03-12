"use client";

import { useState, useEffect, useRef } from "react";
import { Loader2, Brain } from "lucide-react";
import { suggestPersons, getPerson, getRelationshipMap } from "@/lib/api";
import type { PersonProfile, PersonSummary } from "@/lib/types";

export default function ComparePage() {
  const [searchLeft, setSearchLeft] = useState("");
  const [searchRight, setSearchRight] = useState("");
  const [suggestionsLeft, setSuggestionsLeft] = useState<PersonSummary[]>([]);
  const [suggestionsRight, setSuggestionsRight] = useState<PersonSummary[]>([]);
  const [openLeft, setOpenLeft] = useState(false);
  const [openRight, setOpenRight] = useState(false);
  const [personLeft, setPersonLeft] = useState<PersonProfile | null>(null);
  const [personRight, setPersonRight] = useState<PersonProfile | null>(null);
  const [loadingLeft, setLoadingLeft] = useState(false);
  const [loadingRight, setLoadingRight] = useState(false);
  const debounceRef = useRef<Record<string, NodeJS.Timeout>>({});
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (leftRef.current && !leftRef.current.contains(e.target as Node)) setOpenLeft(false);
      if (rightRef.current && !rightRef.current.contains(e.target as Node)) setOpenRight(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function fetchSuggestions(search: string, side: "left" | "right") {
    if (!search || search.length < 2) {
      if (side === "left") setSuggestionsLeft([]);
      else setSuggestionsRight([]);
      return;
    }
    const key = side;
    if (debounceRef.current[key]) clearTimeout(debounceRef.current[key]);
    debounceRef.current[key] = setTimeout(async () => {
      try {
        const items = await suggestPersons(search, 10);
        if (side === "left") {
          setSuggestionsLeft(items);
          setOpenLeft(items.length > 0);
        } else {
          setSuggestionsRight(items);
          setOpenRight(items.length > 0);
        }
      } catch {
        if (side === "left") setSuggestionsLeft([]);
        else setSuggestionsRight([]);
      }
    }, 300);
  }

  useEffect(() => {
    fetchSuggestions(searchLeft, "left");
  }, [searchLeft]);

  useEffect(() => {
    fetchSuggestions(searchRight, "right");
  }, [searchRight]);

  async function selectPerson(side: "left" | "right", p: PersonSummary) {
    if (side === "left") {
      setSearchLeft(p.name);
      setOpenLeft(false);
      setSuggestionsLeft([]);
      setLoadingLeft(true);
      try {
        const profile = await getPerson(p.id);
        setPersonLeft(profile);
      } catch {
        setPersonLeft(null);
      } finally {
        setLoadingLeft(false);
      }
    } else {
      setSearchRight(p.name);
      setOpenRight(false);
      setSuggestionsRight([]);
      setLoadingRight(true);
      try {
        const profile = await getPerson(p.id);
        setPersonRight(profile);
      } catch {
        setPersonRight(null);
      } finally {
        setLoadingRight(false);
      }
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [relationship, setRelationship] = useState<Record<string, any> | null>(null);
  const [relLoading, setRelLoading] = useState(false);

  const expertiseLeftArr = personLeft?.expertise || [];
  const expertiseRightArr = personRight?.expertise || [];
  const expertiseRight = new Set(expertiseRightArr);
  const expertiseLeft = new Set(expertiseLeftArr);
  const overlap = expertiseLeftArr.filter((e) => expertiseRight.has(e));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Compare Persons</h1>

      {/* Search inputs */}
      <div className="grid grid-cols-2 gap-6">
        <div ref={leftRef} className="relative">
          <label className="text-sm text-gray-400 block mb-1">Person A</label>
          <input
            value={searchLeft}
            onChange={(e) => setSearchLeft(e.target.value)}
            onFocus={() => suggestionsLeft.length > 0 && setOpenLeft(true)}
            placeholder="Type to search..."
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {openLeft && suggestionsLeft.length > 0 && (
            <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1a1a] border border-white/10 rounded-lg shadow-xl overflow-hidden">
              {suggestionsLeft.map((s) => (
                <button
                  key={s.id}
                  className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 transition-colors"
                  onClick={() => selectPerson("left", s)}
                >
                  {s.name}
                  {s.company && <span className="text-gray-500"> — {s.company}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
        <div ref={rightRef} className="relative">
          <label className="text-sm text-gray-400 block mb-1">Person B</label>
          <input
            value={searchRight}
            onChange={(e) => setSearchRight(e.target.value)}
            onFocus={() => suggestionsRight.length > 0 && setOpenRight(true)}
            placeholder="Type to search..."
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {openRight && suggestionsRight.length > 0 && (
            <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[#1a1a1a] border border-white/10 rounded-lg shadow-xl overflow-hidden">
              {suggestionsRight.map((s) => (
                <button
                  key={s.id}
                  className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 transition-colors"
                  onClick={() => selectPerson("right", s)}
                >
                  {s.name}
                  {s.company && <span className="text-gray-500"> — {s.company}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {loadingLeft && (
        <div className="text-center text-gray-400 text-sm">Loading Person A...</div>
      )}
      {loadingRight && (
        <div className="text-center text-gray-400 text-sm">Loading Person B...</div>
      )}

      {/* Side-by-side comparison */}
      {personLeft && personRight && (
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-white/5 rounded-xl border border-white/10 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white">{personLeft.name}</h2>
            <CompareValue
              label="Role"
              value={personLeft.current_role || "—"}
              matches={personLeft.current_role === personRight.current_role}
            />
            <CompareValue
              label="Company"
              value={personLeft.company || "—"}
              matches={personLeft.company === personRight.company}
            />
            <CompareValue
              label="Confidence"
              value={`${(personLeft.confidence_score * 100).toFixed(0)}%`}
              matches={personLeft.confidence_score === personRight.confidence_score}
            />
            <CompareValue
              label="Bio"
              value={(personLeft.bio || "—").slice(0, 200)}
              matches={(personLeft.bio || "") === (personRight.bio || "")}
            />
            <div>
              <p className="text-xs text-gray-500 mb-1">Expertise</p>
              <div className="flex flex-wrap gap-1">
                {(personLeft.expertise || []).map((e) => (
                  <span
                    key={e}
                    className={`px-2 py-0.5 rounded text-xs ${
                      overlap.includes(e)
                        ? "bg-emerald-500/20 text-emerald-400"
                        : "bg-amber-500/20 text-amber-400"
                    }`}
                  >
                    {e}
                  </span>
                ))}
              </div>
            </div>
            <CompareValue
              label="Sources count"
              value={String(personLeft.sources?.length ?? 0)}
              matches={(personLeft.sources?.length ?? 0) === (personRight.sources?.length ?? 0)}
            />
            <CompareValue
              label="Career timeline length"
              value={String((personLeft.career_timeline || []).length)}
              matches={
                (personLeft.career_timeline || []).length ===
                (personRight.career_timeline || []).length
              }
            />
          </div>
          <div className="bg-white/5 rounded-xl border border-white/10 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white">{personRight.name}</h2>
            <CompareValue
              label="Role"
              value={personRight.current_role || "—"}
              matches={personLeft.current_role === personRight.current_role}
            />
            <CompareValue
              label="Company"
              value={personRight.company || "—"}
              matches={personLeft.company === personRight.company}
            />
            <CompareValue
              label="Confidence"
              value={`${(personRight.confidence_score * 100).toFixed(0)}%`}
              matches={personLeft.confidence_score === personRight.confidence_score}
            />
            <CompareValue
              label="Bio"
              value={(personRight.bio || "—").slice(0, 200)}
              matches={(personLeft.bio || "") === (personRight.bio || "")}
            />
            <div>
              <p className="text-xs text-gray-500 mb-1">Expertise</p>
              <div className="flex flex-wrap gap-1">
                {(personRight.expertise || []).map((e) => (
                  <span
                    key={e}
                    className={`px-2 py-0.5 rounded text-xs ${
                      overlap.includes(e)
                        ? "bg-emerald-500/20 text-emerald-400"
                        : "bg-amber-500/20 text-amber-400"
                    }`}
                  >
                    {e}
                  </span>
                ))}
              </div>
            </div>
            <CompareValue
              label="Sources count"
              value={String(personRight.sources?.length ?? 0)}
              matches={(personLeft.sources?.length ?? 0) === (personRight.sources?.length ?? 0)}
            />
            <CompareValue
              label="Career timeline length"
              value={String((personRight.career_timeline || []).length)}
              matches={
                (personLeft.career_timeline || []).length ===
                (personRight.career_timeline || []).length
              }
            />
          </div>
        </div>
      )}

      {/* AI Relationship Analysis */}
      {personLeft && personRight && (
        <div className="bg-white/5 rounded-xl border border-white/10 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Brain size={20} className="text-purple-400" />
              AI Relationship Analysis
            </h2>
            <button
              onClick={async () => {
                setRelLoading(true);
                try {
                  const result = await getRelationshipMap(personLeft.id, personRight.id);
                  setRelationship(result);
                } catch {
                  setRelationship({ error: "Analysis failed" });
                } finally {
                  setRelLoading(false);
                }
              }}
              disabled={relLoading}
              className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {relLoading ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
              {relLoading ? "Analyzing..." : relationship ? "Re-analyze" : "Analyze Relationship"}
            </button>
          </div>
          {relationship && !relationship.error && (
            <div className="space-y-3">
              <div className="flex gap-4 flex-wrap">
                <div className="bg-white/5 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-500">Relationship</p>
                  <p className="text-sm text-white font-medium capitalize">{relationship.relationship_type?.replace(/_/g, " ")}</p>
                </div>
                <div className="bg-white/5 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-500">Connection</p>
                  <p className="text-sm text-white font-medium">{((relationship.connection_strength || 0) * 100).toFixed(0)}%</p>
                </div>
                <div className="bg-white/5 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-500">Collaboration</p>
                  <p className="text-sm text-white font-medium capitalize">{relationship.collaboration_potential}</p>
                </div>
              </div>
              {relationship.summary && (
                <p className="text-sm text-gray-300">{relationship.summary}</p>
              )}
              {relationship.collaboration_areas?.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Collaboration Areas</p>
                  <div className="flex flex-wrap gap-1">
                    {relationship.collaboration_areas.map((a: string, i: number) => (
                      <span key={i} className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 text-xs">{a}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {relationship?.error && (
            <p className="text-red-400 text-sm">{relationship.error}</p>
          )}
        </div>
      )}

      {(!personLeft || !personRight) && (
        <div className="text-center py-12 text-gray-500">
          {!personLeft && !personRight
            ? "Select both persons to compare"
            : "Select the other person to compare"}
        </div>
      )}
    </div>
  );
}

function CompareValue({
  label,
  value,
  matches,
}: {
  label: string;
  value: string;
  matches: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-sm ${matches ? "text-emerald-400" : "text-amber-400"}`}>{value}</p>
    </div>
  );
}
