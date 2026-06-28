import Link from "next/link";
import { capabilityTags, demoTask } from "./demoData";

export function WorkbenchShell({
  mode,
  title,
  summary,
  children,
}: {
  mode: string;
  title: string;
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-[calc(100vh-160px)] bg-[#f7f9fc] text-slate-950">
      <div className="mx-auto max-w-7xl px-5 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/style-lab" className="text-xs font-medium text-slate-400 hover:text-cyan-600">
              返回 Style Lab
            </Link>
            <h1 className="mt-1 text-2xl font-semibold">{title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{summary}</p>
          </div>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-500">
            {mode}
          </span>
        </div>

        <TaskCommand />
        {children}
      </div>
    </div>
  );
}

export function TaskCommand() {
  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-600">Task Command</span>
        <div className="flex gap-2 text-xs text-slate-500">
          <span className="rounded-full bg-slate-100 px-3 py-1">{demoTask.intent}</span>
          <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-700">风险 {demoTask.risk}</span>
        </div>
      </div>
      <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
        <p className="text-lg leading-8 text-slate-900">{demoTask.prompt}</p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {capabilityTags.map(tag => (
          <span key={tag} className="rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700">
            {tag}
          </span>
        ))}
      </div>
    </section>
  );
}

export function Panel({
  title,
  eyebrow,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {eyebrow && <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-600">{eyebrow}</p>}
      <h2 className={eyebrow ? "mt-2 text-base font-semibold text-slate-950" : "text-base font-semibold text-slate-950"}>
        {title}
      </h2>
      {children}
    </section>
  );
}

export function AgentNode({
  name,
  role,
  match,
  signal,
  tools,
  accent = "cyan",
}: {
  name: string;
  role: string;
  match: number;
  signal: string;
  tools: string[];
  accent?: "cyan" | "slate" | "amber";
}) {
  const accentClass = accent === "amber" ? "bg-amber-500" : accent === "slate" ? "bg-slate-950" : "bg-cyan-500";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">{role}</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-950">{name}</h3>
        </div>
        <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">{match}%</span>
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-500">{signal}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {tools.map(tool => (
          <span key={tool} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600">{tool}</span>
        ))}
      </div>
      <div className="mt-5 h-2 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${accentClass}`} style={{ width: `${match}%` }} />
      </div>
    </div>
  );
}
