import { AgentNode, Panel, WorkbenchShell } from "@/components/style-lab/CleanWorkbench";
import { demoAgents, demoTask, routingSteps } from "@/components/style-lab/demoData";

export default function SmartRoutingDemo() {
  const lead = demoAgents[0];
  const support = demoAgents.slice(1);

  return (
    <WorkbenchShell
      mode="Matching A"
      title="智能路由型"
      summary="平台弱化选择过程，直接根据任务画像给出推荐回答阵容。适合用户只想快速得到结果的场景。"
    >
      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Panel title="推荐阵容" eyebrow="Auto Route">
          <div className="mt-5 rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-700">Primary Agent</p>
                <h3 className="mt-2 text-2xl font-semibold text-slate-950">{lead.name}</h3>
                <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">{lead.signal}</p>
              </div>
              <div className="rounded-lg bg-white px-4 py-3 text-right shadow-sm">
                <p className="text-3xl font-semibold text-cyan-600">{lead.match}%</p>
                <p className="text-xs text-slate-400">match</p>
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {support.map(agent => (
              <AgentNode
                key={agent.name}
                name={agent.name}
                role={agent.role}
                match={agent.match}
                signal={agent.signal}
                tools={agent.tools}
                accent="slate"
              />
            ))}
          </div>
        </Panel>

        <Panel title="用户看到的解释" eyebrow="Minimal Explainability">
          <div className="mt-5 space-y-3">
            <ExplainLine label="为什么这样选" value="这个任务需要产品策略主导，架构与风险审查辅助。" />
            <ExplainLine label="预计产出" value={demoTask.output} />
            <ExplainLine label="预计消耗" value={demoTask.budget} />
          </div>
          <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-900">路由过程被折叠</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {routingSteps.map(step => (
                <span key={step} className="rounded-full bg-white px-3 py-1 text-xs text-slate-500 shadow-sm">
                  {step}
                </span>
              ))}
            </div>
          </div>
        </Panel>
      </div>
    </WorkbenchShell>
  );
}

function ExplainLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}
