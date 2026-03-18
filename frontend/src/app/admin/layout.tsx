"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import {
  Users,
  DollarSign,
  LogOut,
  Zap,
  Key,
  Webhook,
  GitCompare,
  Loader2,
  Menu,
  X,
  Book,
  Upload,
  List,
  BarChart3,
  Shield,
  Network,
  Clock,
} from "lucide-react";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);
  const [checking, setChecking] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token") || localStorage.getItem("admin_token");
    if (!token) {
      router.push("/login");
    } else {
      setAuthed(true);
    }
    setChecking(false);
  }, [router]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  if (checking) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0a0a0a]">
        <Loader2 size={32} className="animate-spin text-blue-500" />
      </div>
    );
  }

  if (!authed) return null;

  const links = [
    { href: "/admin", label: "Persons", icon: Users },
    { href: "/admin/lists", label: "Saved Lists", icon: List },
    { href: "/admin/costs", label: "Cost Dashboard", icon: DollarSign },
    { href: "/admin/analytics", label: "Usage Analytics", icon: BarChart3 },
    { href: "/admin/audit", label: "Audit Log", icon: Shield },
    { href: "/admin/api-keys", label: "API Keys", icon: Key },
    { href: "/admin/webhooks", label: "Webhooks", icon: Webhook },
    { href: "/admin/batch", label: "Batch Discovery", icon: Upload },
    { href: "/admin/staleness", label: "Auto-Refresh", icon: Clock },
    { href: "/admin/compare", label: "Compare", icon: GitCompare },
    { href: "/admin/network", label: "Network Graph", icon: Network },
    { href: "/admin/docs", label: "API Docs", icon: Book },
  ];

  const sidebar = (
    <>
      <div className="flex items-center gap-2 mb-8">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
        <span className="text-sm font-bold text-white">Admin Dashboard</span>
      </div>
      <nav className="flex-1 space-y-1">
        {links.map(({ href, label, icon: Icon }) => {
          const isActive =
            href === "/admin"
              ? pathname === "/admin" || pathname.startsWith("/admin/persons")
              : pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-white/10 text-white"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
      <button
        onClick={() => {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("admin_token");
          router.push("/login");
        }}
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-white/5 transition-colors"
      >
        <LogOut size={16} />
        Logout
      </button>
    </>
  );

  return (
    <div className="h-screen flex bg-[#0a0a0a]">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-56 border-r border-white/10 p-4 flex-col bg-black/20">
        {sidebar}
      </aside>

      {/* Mobile hamburger */}
      <button
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-lg bg-white/10 text-white"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 bg-black/60 z-40"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="md:hidden fixed left-0 top-0 h-full w-56 border-r border-white/10 p-4 flex flex-col bg-[#0a0a0a] z-50">
            {sidebar}
          </aside>
        </>
      )}

      <main className="flex-1 overflow-auto p-4 md:p-6 bg-[#0a0a0a]">{children}</main>
    </div>
  );
}
