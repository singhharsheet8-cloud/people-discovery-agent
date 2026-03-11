"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, RefreshCw } from "lucide-react";
import { getPerson, updatePerson, reSearchPerson } from "@/lib/api";
import type { PersonProfile } from "@/lib/types";

export default function EditPersonPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;
  const [person, setPerson] = useState<PersonProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reSearching, setReSearching] = useState(false);
  const [form, setForm] = useState({
    name: "",
    current_role: "",
    company: "",
    location: "",
    bio: "",
  });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPerson(id)
      .then((p) => {
        if (!cancelled) {
          setPerson(p);
          setForm({
            name: p.name || "",
            current_role: p.current_role || "",
            company: p.company || "",
            location: p.location || "",
            bio: p.bio || "",
          });
        }
      })
      .catch(() => {
        if (!cancelled) setPerson(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await updatePerson(id, {
        name: form.name || undefined,
        current_role: form.current_role || undefined,
        company: form.company || undefined,
        location: form.location || undefined,
        bio: form.bio || undefined,
      });
      router.push(`/admin/persons/${id}`);
    } catch {
      setSaving(false);
    }
  };

  const handleReSearch = async () => {
    setReSearching(true);
    try {
      await reSearchPerson(id);
      router.push(`/admin/persons/${id}`);
    } catch {
      setReSearching(false);
    }
  };

  if (loading || !person) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-gray-500">
        {loading ? "Loading..." : "Person not found"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href={`/admin/persons/${id}`}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft size={18} />
          Back
        </Link>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
        <h1 className="text-xl font-bold text-white mb-6">Edit Person</h1>

        <form onSubmit={handleSave} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Current Role
            </label>
            <input
              type="text"
              value={form.current_role}
              onChange={(e) =>
                setForm((f) => ({ ...f, current_role: e.target.value }))
              }
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Company
            </label>
            <input
              type="text"
              value={form.company}
              onChange={(e) =>
                setForm((f) => ({ ...f, company: e.target.value }))
              }
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Location
            </label>
            <input
              type="text"
              value={form.location}
              onChange={(e) =>
                setForm((f) => ({ ...f, location: e.target.value }))
              }
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Bio
            </label>
            <textarea
              value={form.bio}
              onChange={(e) => setForm((f) => ({ ...f, bio: e.target.value }))}
              rows={5}
              className="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 resize-none"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              <Save size={16} />
              Save
            </button>
            <button
              type="button"
              onClick={handleReSearch}
              disabled={reSearching}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 text-white hover:bg-white/15 disabled:opacity-50 transition-colors"
            >
              <RefreshCw
                size={16}
                className={reSearching ? "animate-spin" : ""}
              />
              Re-search with corrections
            </button>
            <Link
              href={`/admin/persons/${id}`}
              className="px-4 py-2 rounded-lg bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
