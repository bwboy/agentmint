import Link from "next/link";
import { capabilityTags, demoAgents, demoTask, routingSteps } from "@/components/style-lab/demoData";

export default function StyleC() {
  return (
    <div className="min-h-[calc(100vh-160px)] bg-[#eef4ff] text-slate-950">
      <div className="mx-auto max-w-7xl px-5 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/style-lab" className="text-xs font-medium text-slate-500 hover:text-blue-600">返回 Style Lab</Link>
            <h1 className="mt-1 text-2xl font-semibold">Futuristic Glass Console</h1>
          </div>
          <span className="rounded-full border border-blue-300 bg-white/60 px-3 py-1 text-xs font-medium text-blue-700">
            Style C
          </span>
        </div>

        <section className="rounded-lg border border-white/80 bg-white/55 p-5 shadow-xl shadow-blue-900/10 backdrop-blur">
          <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-lg border border-white/80 bg-white/55 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-600">Neural Console</p>
              <h2 className="mt-3 text-3xl font-semibold leading-tight">任务意图已解析，正在生成 Agent 信号图</h2>
              <p className="mt-4 rounded-md border border-blue-100 bg-white/70 p-4 text-base leading-7 text-slate-700">
                {demoTask.prompt}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {capabilityTags.map(tag => (
                  <span key={tag} className="rounded-full border border-blue-200 bg-white/70 px-3 py-1 text-xs font-medium text-blue-700">
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <GlassMetric label="Intent" value={demoTask.intent} />
              <GlassMetric label="Output" value={demoTask.output} />
              <GlassMetric label="Risk" value={demoTask.risk} />
              <GlassMetric label="Confidence" value={`${demoTask.confidence}%`} />
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="rounded-lg border border-white/80 bg-white/50 p-5 shadow-lg shadow-blue-900/5 backdrop-blur">
            <h2 className="text-sm font-semibold text-slate-900">Signal Pipeline</h2>
            <div className="mt-5 space-y-3">
              {routingSteps.map((step, index) => (
                <div key={step} className="flex items-center gap-3 rounded-md border border-blue-100 bg-white/60 p-3">
                  <span className="grid size-8 place-items-center rounded-md bg-blue-600 text-xs font-semibold text-white">{index + 1}</span>
                  <div>
                    <p className="text-sm font-medium text-slate-800">{step}</p>
                    <p className="text-xs text-slate-500">更新任务向量与能力权重</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {demoAgents.map(agent => (
              <div key={agent.name} className="rounded-lg border border-white/80 bg-white/55 p-4 shadow-lg shadow-blue-900/5 backdrop-blur">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-blue-500">{agent.role}</p>
                    <h3 className="mt-2 text-lg font-semibold text-slate-950">{agent.name}</h3>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-semibold text-blue-700">{agent.match}</p>
                    <p className="text-[10px] uppercase tracking-[0.16em] text-slate-400">signal</p>
                  </div>
                </div>
                <p className="mt-4 text-sm leading-6 text-slate-600">{agent.signal}</p>
                <div className="mt-4 grid gap-2">
                  {agent.tools.map(tool => (
                    <div key={tool} className="rounded-md border border-blue-100 bg-white/55 px-3 py-2 text-xs text-slate-600">
                      {tool}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function GlassMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/80 bg-white/50 p-4 shadow-lg shadow-blue-900/5 backdrop-blur">
      <p className="text-xs uppercase tracking-[0.18em] text-blue-500">{label}</p>
      <p className="mt-3 text-base font-semibold text-slate-900">{value}</p>
    </div>
  );
}
