import Link from "next/link";
import { capabilityTags, demoAgents, demoTask, routingSteps } from "@/components/style-lab/demoData";

export default function StyleB() {
  return (
    <div className="min-h-[calc(100vh-160px)] bg-[#090b10] text-zinc-100">
      <div className="mx-auto max-w-7xl px-5 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/style-lab" className="text-xs font-medium text-zinc-500 hover:text-lime-300">返回 Style Lab</Link>
            <h1 className="mt-1 text-2xl font-semibold">Dark Agent Arena</h1>
          </div>
          <span className="rounded-full border border-lime-300/30 bg-lime-300/10 px-3 py-1 text-xs font-medium text-lime-200">
            Style B
          </span>
        </div>

        <section className="rounded-lg border border-zinc-800 bg-[#10131a] p-5 shadow-2xl shadow-black/30">
          <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-lime-300">Live Draft</p>
              <h2 className="mt-3 text-4xl font-semibold leading-tight">为这次任务组建 Agent 阵容</h2>
              <p className="mt-4 text-sm leading-6 text-zinc-400">{demoTask.prompt}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {capabilityTags.map(tag => (
                  <span key={tag} className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-300">
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <ArenaMetric label="Intent" value={demoTask.intent} />
              <ArenaMetric label="Budget" value={demoTask.budget} />
              <ArenaMetric label="Risk" value={demoTask.risk} />
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-[0.75fr_1.25fr]">
          <div className="rounded-lg border border-zinc-800 bg-[#10131a] p-5">
            <h2 className="text-sm font-semibold text-zinc-100">Match Engine</h2>
            <div className="mt-5 space-y-3">
              {routingSteps.map((step, index) => (
                <div key={step} className="rounded-md border border-zinc-800 bg-black/20 p-3">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-lime-300">0{index + 1}</span>
                    <p className="text-sm text-zinc-200">{step}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {demoAgents.map(agent => (
              <div key={agent.name} className="rounded-lg border border-zinc-800 bg-[#10131a] p-4">
                <div className="mb-5 flex items-center justify-between">
                  <span className="rounded bg-lime-300 px-2 py-1 text-xs font-bold text-black">{agent.match}</span>
                  <span className="text-xs uppercase tracking-[0.16em] text-zinc-500">picked</span>
                </div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-lime-300">{agent.role}</p>
                <h3 className="mt-2 text-xl font-semibold">{agent.name}</h3>
                <p className="mt-4 min-h-24 text-sm leading-6 text-zinc-400">{agent.signal}</p>
                <div className="mt-4 border-t border-zinc-800 pt-4">
                  <p className="text-xs text-zinc-500">Style</p>
                  <p className="mt-1 text-sm text-zinc-300">{agent.tone}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function ArenaMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-black/20 p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-zinc-500">{label}</p>
      <p className="mt-4 text-lg font-semibold text-zinc-100">{value}</p>
    </div>
  );
}
