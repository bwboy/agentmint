import { AgentNode, Panel, WorkbenchShell } from "@/components/style-lab/CleanWorkbench";
import { demoAgents, routingSignals, routingSteps } from "@/components/style-lab/demoData";

export default function TransparentCastingDemo() {
  return (
    <WorkbenchShell
      mode="Matching B"
      title="选角透明型"
      summary="平台把匹配理由摊开，用户能看到领域、能力、历史表现、成本效率如何影响 Agent 阵容。适合强调 Agent 能力差异。"
    >
      <div className="grid gap-5 lg:grid-cols-[0.82fr_1.18fr]">
        <Panel title="匹配信号" eyebrow="Casting Signals">
          <div className="mt-5 grid gap-3">
            {routingSignals.map(signal => (
              <div key={signal.label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{signal.label}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">{signal.detail}</p>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-sm font-semibold text-cyan-600 shadow-sm">
                    {signal.value}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Agent 选角板" eyebrow="Why These Agents">
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {demoAgents.map((agent, index) => (
              <AgentNode
                key={agent.name}
                name={agent.name}
                role={agent.role}
                match={agent.match}
                signal={agent.signal}
                tools={agent.tools}
                accent={index === 2 ? "amber" : "cyan"}
              />
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="可解释路由链路" eyebrow="Trace" className="mt-5">
        <div className="mt-5 grid gap-3 md:grid-cols-5">
          {routingSteps.map((step, index) => (
            <div key={step} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <span className="grid size-8 place-items-center rounded-full bg-slate-950 text-xs font-semibold text-white">{index + 1}</span>
              <p className="mt-4 text-sm font-medium text-slate-900">{step}</p>
              <p className="mt-2 text-xs leading-5 text-slate-500">用户可展开查看该步骤影响了哪些 Agent。</p>
            </div>
          ))}
        </div>
      </Panel>
    </WorkbenchShell>
  );
}
