import Link from "next/link";
import { capabilityTags, demoAgents, demoTask, routingSteps } from "@/components/style-lab/demoData";

export default function StyleA() {
  return (
    <div className="min-h-[calc(100vh-160px)] bg-[#f7f9fc] text-slate-950">
      <div className="mx-auto max-w-7xl px-5 py-8">
        <TopBar label="Style A" title="Clean AI Workbench" />

        <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-600">Command</span>
              <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700">3 agents online</span>
            </div>
            <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
              <p className="text-lg leading-8 text-slate-900">{demoTask.prompt}</p>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Signal label="Intent" value={demoTask.intent} />
              <Signal label="Output" value={demoTask.output} />
              <Signal label="Confidence" value={`${demoTask.confidence}%`} />
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {capabilityTags.map(tag => (
                <span key={tag} className="rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700">
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-900">Routing Trace</h2>
            <div className="mt-5 space-y-4">
              {routingSteps.map((step, index) => (
                <div key={step} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <span className="grid size-7 place-items-center rounded-full bg-slate-950 text-xs font-semibold text-white">{index + 1}</span>
                    {index < routingSteps.length - 1 && <span className="mt-2 h-6 w-px bg-slate-200" />}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-800">{step}</p>
                    <p className="text-xs text-slate-400">基于任务画像更新候选集合</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-3">
          {demoAgents.map(agent => (
            <div key={agent.name} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">{agent.role}</p>
                  <h3 className="mt-1 text-lg font-semibold text-slate-950">{agent.name}</h3>
                </div>
                <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">{agent.match}%</span>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-500">{agent.signal}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {agent.tools.map(tool => (
                  <span key={tool} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600">{tool}</span>
                ))}
              </div>
              <div className="mt-5 h-2 rounded-full bg-slate-100">
                <div className="h-2 rounded-full bg-cyan-500" style={{ width: `${agent.match}%` }} />
              </div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function TopBar({ label, title }: { label: string; title: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <Link href="/style-lab" className="text-xs font-medium text-slate-400 hover:text-cyan-600">返回 Style Lab</Link>
        <h1 className="mt-1 text-2xl font-semibold">{title}</h1>
      </div>
      <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-500">{label}</span>
    </div>
  );
}

function Signal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}
