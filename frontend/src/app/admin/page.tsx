"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, ChevronLeft, ChevronRight, Users } from "lucide-react";
import { getPersons } from "@/lib/api";
import type { PersonSummary } from "@/lib/types";
import { confidenceColor } from "@/lib/utils";

const PER_PAGE = 20;

export default function AdminPersonsPage() {
  const router = useRouter();
  const [persons, setPersons] = useState<PersonSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPersons(page, PER_PAGE, search)
      .then((res) => {
        if (!cancelled) {
          setPersons(Array.isArray(res.items) ? res.items : []);
          setTotal(res.total ?? 0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPersons([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, search]);

  const totalPages = Math.ceil(total / PER_PAGE);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  };

  const formatDate = (iso: string) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users size={24} />
          Discovered Persons
        </h1>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
            />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Filter by name or company..."
              className="w-full pl-10 pr-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-white/10 text-white hover:bg-white/15 transition-colors"
          >
            Search
          </button>
        </form>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-gray-500">Loading...</div>
        ) : persons.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            No persons found
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Name
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Company
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Role
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Confidence
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Sources
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Updated
                  </th>
                </tr>
              </thead>
              <tbody>
                {persons.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => router.push(`/admin/persons/${p.id}`)}
                    className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                  >
                    <td className="py-3 px-4">
                      <span className="text-white font-medium">{p.name}</span>
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {p.company || "—"}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {p.current_role || "—"}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`text-sm font-medium ${confidenceColor(
                          p.confidence_score
                        )}`}
                      >
                        {Math.round(p.confidence_score * 100)}%
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {p.sources_count}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-sm">
                      {formatDate(p.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-white/10">
            <p className="text-sm text-gray-500">
              {total} total · Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg bg-white/5 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={18} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg bg-white/5 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
