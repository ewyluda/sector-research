"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import clsx from "clsx";

const links = [
  { href: "/",            label: "Today"       },
  { href: "/status",      label: "Status"      },
  { href: "/themes",      label: "Themes"      },
  { href: "/filings",     label: "Filings"     },
  { href: "/performance", label: "Performance" },
  { href: "/library",     label: "Library"     },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [tickerInput, setTickerInput] = useState("");

  function goToCompany(e: React.FormEvent) {
    e.preventDefault();
    const t = tickerInput.trim().toUpperCase();
    if (t) {
      router.push(`/company/${encodeURIComponent(t)}`);
      setTickerInput("");
    }
  }

  return (
    <>
    <a href="#main-content" className="skip-link">Skip to main content</a>
    <header data-print-hide="true" className="border-b border-[var(--border)] bg-[var(--surface)] sticky top-0 z-40">
      <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center justify-between">
        {/* Wordmark */}
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="w-2 h-2 rounded-full bg-[var(--primary)]" />
          <span className="hidden sm:inline font-semibold text-sm tracking-tight text-[var(--primary-dk)] whitespace-nowrap">
            Sector Research
          </span>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "px-3 py-1.5 rounded-md text-sm whitespace-nowrap transition-colors",
                path === href || (href !== "/" && path.startsWith(href))
                  ? "bg-[var(--accent-bg)] text-[var(--primary-dk)] font-medium"
                  : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-alt)]"
              )}
            >
              {label}
            </Link>
          ))}
          <form onSubmit={goToCompany} className="ml-2">
            <input
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              placeholder="Ticker…"
              className="w-24 rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)]"
              aria-label="Go to company workspace"
            />
          </form>
          <button
            type="button"
            onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
            className="ml-1 text-[10px] font-mono text-[var(--text-faint)] border border-[var(--border)] rounded px-1.5 py-0.5 hover:text-[var(--text-muted)] cursor-pointer"
            aria-label="Open command palette"
          >
            ⌘K
          </button>
        </nav>
      </div>
    </header>
    </>
  );
}
