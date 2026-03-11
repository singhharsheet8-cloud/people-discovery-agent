"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Users, DollarSign, LogOut, Zap, Key, Webhook, GitCompare } from "lucide-react";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("admin_token");
    if (!token) {
      router.push("/login");
    } else {
      setAuthed(true);
    }
  }, [router]);

  if (!authed) return null;

  const links = [
    { href: "/admin", label: "Persons", icon: Users },
    { href: "/admin/costs", label: "Cost Dashboard", icon: DollarSign },
    { href: "/admin/api-keys", label: "API Keys", icon: Key },
    { href: "/admin/webhooks", label: "Webhooks", icon: Webhook },
    { href: "/admin/compare", label: "Compare", icon: GitCompare },
  ];

  return (
    <div className="h-screen flex bg-[#0a0a0a]">
      <aside className="w-56 border-r border-white/10 p-4 flex flex-col bg-black/20">
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
            localStorage.removeItem("admin_token");
            router.push("/login");
          }}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-white/5 transition-colors"
        >
          <LogOut size={16} />
          Logout
        </button>
      </aside>
      <main className="flex-1 overflow-auto p-6 bg-[#0a0a0a]">{children}</main>
    </div>
  );
}
