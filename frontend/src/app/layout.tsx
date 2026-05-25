import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { Suspense } from "react";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Attribution Dashboard",
  description: "GHL × Meta × CRM — Sistema de Atribuição de Funil",
};

const NAV = [
  { href: "/",        label: "📊 Ranking" },
  { href: "/funnel",  label: "🔽 Funil" },
  { href: "/team",    label: "👥 Time" },
  { href: "/quality", label: "🔍 Qualidade" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className={`${inter.className} bg-gray-50 min-h-screen`}>
        {/* Sidebar */}
        <div className="flex h-screen overflow-hidden">
          <nav className="w-52 bg-gray-900 text-white flex flex-col shrink-0">
            <div className="px-4 py-5 border-b border-gray-700">
              <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Attribution</p>
              <p className="text-sm font-semibold mt-0.5">Dashboard v2</p>
            </div>
            <div className="flex-1 py-4">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
                >
                  {item.label}
                </Link>
              ))}
            </div>
            <div className="px-4 py-3 border-t border-gray-700 text-xs text-gray-500">
              Blueprint v2 — GHL × Meta × CRM
            </div>
          </nav>

          {/* Main */}
          <main className="flex-1 overflow-y-auto">
            <Suspense>{children}</Suspense>
          </main>
        </div>
      </body>
    </html>
  );
}
