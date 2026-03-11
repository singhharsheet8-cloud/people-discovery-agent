"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import {
  Search,
  User,
  Building,
  MapPin,
  Globe,
  Github,
  Twitter,
  FileText,
  Loader2,
  CheckCircle,
  ExternalLink,
  Zap,
} from "lucide-react";
import { discoverPerson, getJob } from "@/lib/api";
import type { DiscoverRequest, PersonProfile } from "@/lib/types";
import { ApiDocsPanel } from "@/components/api-docs-panel";
import { PersonProfile as PersonProfileComponent } from "@/components/person-profile";

const POLL_INTERVAL_MS = 2000;

const initialForm: DiscoverRequest = {
  name: "",
  company: "",
  role: "",
  location: "",
  linkedin_url: "",
  twitter_handle: "",
  github_username: "",
  context: "",
};

export default function Home() {
  const [form, setForm] = useState<DiscoverRequest>(initialForm);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [profile, setProfile] = useState<PersonProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const updateField = useCallback(
    (field: keyof DiscoverRequest, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setError(null);
    },
    []
  );

  const pollJob = useCallback(async (id: string) => {
    try {
      const job = await getJob(id);
      if (job.status === "completed" && job.profile) {
        setProfile(job.profile);
        setJobId(null);
        setIsDiscovering(false);
        return;
      }
      if (job.status === "failed" && job.error_message) {
        setError(job.error_message);
        setJobId(null);
        setIsDiscovering(false);
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch job status");
    }
  }, []);

  const handleDiscover = useCallback(async () => {
    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    setError(null);
    setProfile(null);
    setIsDiscovering(true);
    try {
      const res = await discoverPerson(form);
      setJobId(res.job_id);
      if (res.job_id) {
        pollJob(res.job_id);
      } else {
        setIsDiscovering(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
      setIsDiscovering(false);
    }
  }, [form, pollJob]);

  useEffect(() => {
    if (!jobId || !isDiscovering) return;
    const interval = setInterval(() => pollJob(jobId), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [jobId, isDiscovering, pollJob]);

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-gray-100">
      {/* Header */}
      <header className="border-b border-white/10 px-4 py-4 sm:px-6">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center">
              <Zap size={20} className="text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">People Discovery Platform</h1>
              <p className="text-xs text-gray-500">API-first deep person intelligence</p>
            </div>
          </div>
          <Link
            href="/admin"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors"
          >
            Admin
            <ExternalLink size={14} />
          </Link>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Form */}
          <div className="space-y-6">
            <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.06] to-transparent p-6 sm:p-8">
              <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
                <Search size={20} className="text-brand-400" />
                Discover a Person
              </h2>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleDiscover();
                }}
                className="space-y-4"
              >
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">
                    Name <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <User
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                    />
                    <input
                      type="text"
                      value={form.name}
                      onChange={(e) => updateField("name", e.target.value)}
                      placeholder="e.g. Jane Smith"
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                      Company
                    </label>
                    <div className="relative">
                      <Building
                        size={16}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                      />
                      <input
                        type="text"
                        value={form.company}
                        onChange={(e) => updateField("company", e.target.value)}
                        placeholder="e.g. Acme Inc"
                        className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                      Role / Title
                    </label>
                    <div className="relative">
                      <User
                        size={16}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                      />
                      <input
                        type="text"
                        value={form.role}
                        onChange={(e) => updateField("role", e.target.value)}
                        placeholder="e.g. CTO"
                        className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">
                    Location
                  </label>
                  <div className="relative">
                    <MapPin
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                    />
                    <input
                      type="text"
                      value={form.location}
                      onChange={(e) => updateField("location", e.target.value)}
                      placeholder="e.g. San Francisco, CA"
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                      LinkedIn URL
                    </label>
                    <div className="relative">
                      <Globe
                        size={16}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                      />
                      <input
                        type="url"
                        value={form.linkedin_url}
                        onChange={(e) => updateField("linkedin_url", e.target.value)}
                        placeholder="https://linkedin.com/in/..."
                        className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">
                      Twitter Handle
                    </label>
                    <div className="relative">
                      <Twitter
                        size={16}
                        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                      />
                      <input
                        type="text"
                        value={form.twitter_handle}
                        onChange={(e) => updateField("twitter_handle", e.target.value)}
                        placeholder="@username"
                        className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">
                    GitHub Username
                  </label>
                  <div className="relative">
                    <Github
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
                    />
                    <input
                      type="text"
                      value={form.github_username}
                      onChange={(e) => updateField("github_username", e.target.value)}
                      placeholder="username"
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">
                    Additional Context
                  </label>
                  <div className="relative">
                    <FileText
                      size={16}
                      className="absolute left-3 top-3 text-gray-500"
                    />
                    <textarea
                      value={form.context}
                      onChange={(e) => updateField("context", e.target.value)}
                      placeholder="Any extra context to help the search..."
                      rows={3}
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500/50 transition-colors resize-none"
                    />
                  </div>
                </div>

                {error && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isDiscovering}
                  className="w-full py-3 rounded-xl font-semibold text-white bg-gradient-to-r from-brand-500 to-purple-600 hover:from-brand-600 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-brand-500/50 disabled:opacity-60 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
                >
                  {isDiscovering ? (
                    <>
                      <Loader2 size={20} className="animate-spin" />
                      Discovering...
                    </>
                  ) : (
                    <>
                      <Search size={20} />
                      Discover
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* API Docs Panel */}
            <ApiDocsPanel formValues={form} />
          </div>

          {/* Result Panel */}
          <div className="space-y-6">
            {isDiscovering && (
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-8 flex flex-col items-center justify-center gap-4">
                <div className="w-16 h-16 rounded-2xl bg-brand-500/20 flex items-center justify-center">
                  <Loader2 size={32} className="text-brand-400 animate-spin" />
                </div>
                <div className="text-center">
                  <p className="text-white font-medium">Discovering person...</p>
                  <p className="text-sm text-gray-500 mt-1">
                    Polling job status every {POLL_INTERVAL_MS / 1000}s
                  </p>
                </div>
              </div>
            )}

            {profile && !isDiscovering && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-emerald-400">
                  <CheckCircle size={20} />
                  <span className="font-medium">Profile ready</span>
                </div>
                <PersonProfileComponent profile={profile} />
              </div>
            )}

            {!profile && !isDiscovering && !error && (
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-12 text-center">
                <Search size={48} className="mx-auto text-gray-600 mb-4" />
                <p className="text-gray-400">Fill the form and click Discover to get started</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
