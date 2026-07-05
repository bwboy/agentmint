"use client";

import Link from "next/link";
import type { ReactNode } from "react";

type PageShellProps = {
  children: ReactNode;
  narrow?: boolean;
  className?: string;
};

type PageHeaderProps = {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
};

export function PageShell({ children, narrow, className = "" }: PageShellProps) {
  return (
    <div className={`mx-auto ${narrow ? "max-w-3xl" : "max-w-5xl"} space-y-6 px-4 py-8 ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions, compact }: PageHeaderProps) {
  return (
    <section className={`surface-card relative overflow-hidden ${compact ? "p-5 md:p-6" : "p-6 md:p-8"}`}>
      <div className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-40 opacity-60" />
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-sm font-medium text-brand">{eyebrow}</p>
          <h1 className={compact ? "mt-2 text-2xl font-semibold text-ink" : "mt-3 text-4xl font-bold leading-tight tracking-[-0.02em] text-ink md:text-[44px]"}>
            {title}
          </h1>
          {description && <p className="mt-3 text-sm leading-6 text-text-secondary md:text-base">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </section>
  );
}

export function ActionLink({ href, children, tone = "secondary" }: { href: string; children: ReactNode; tone?: "primary" | "secondary" }) {
  return (
    <Link
      href={href}
      className={
        tone === "primary"
          ? "stateful inline-flex h-10 items-center justify-center rounded-md bg-brand px-4 text-sm font-medium text-canvas hover:bg-brand-hover"
          : "stateful inline-flex h-10 items-center justify-center rounded-md border border-border-default bg-elevated px-4 text-sm font-medium text-ink hover:border-brand-selected hover:text-brand"
      }
    >
      {children}
    </Link>
  );
}

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="surface-card p-8 text-center">
      <p className="text-sm text-text-tertiary">{title}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
