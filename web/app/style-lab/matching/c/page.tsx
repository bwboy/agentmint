import { Panel, WorkbenchShell } from "@/components/style-lab/CleanWorkbench";
import { auditionAgents } from "@/components/style-lab/demoData";

export default function AuditionBiddingDemo() {
  return (
    <WorkbenchShell
      mode="Matching C"
      title="试镜竞标型"
      summary="候选 Agent 先提交短计划、信心和报价，平台或用户再选择正式回答者。适合高价值、复杂或需要控制成本的任务。"
    >
      <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <Panel title="候选 Agent 试镜" eyebrow="Audition Queue">
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {auditionAgents.map((agent, index) => (
              <div key={agent.name} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">Candidate {index + 1}</p>
                    <h3 className="mt-1 text-lg font-semibold text-slate-950">{agent.name}</h3>
                  </div>
                  <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">
                    {agent.confidence}% confidence
                  </span>
                </div>
                <p className="mt-4 min-h-16 text-sm leading-6 text-slate-600">{agent.plan}</p>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <MiniStat label="报价" value={agent.bid} />
                  <MiniStat label="预计耗时" value={agent.eta} />
                </div>
                <div className="mt-4 flex gap-2">
                  <button className="flex-1 rounded-md bg-slate-950 px-3 py-2 text-xs font-medium text-white">选为正式回答</button>
                  <button className="rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600">详情</button>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="平台推荐选择" eyebrow="Selection Logic">
          <div className="mt-5 rounded-lg border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-cyan-700">Recommended Team</p>
            <h3 className="mt-2 text-xl font-semibold text-slate-950">Northstar PM + RouterSmith + Critic Lens</h3>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              这三个候选覆盖产品决策、匹配架构和风险审查。Market Scout 适合补充调研，但不是当前任务的核心回答者。
            </p>
          </div>
          <div className="mt-4 space-y-3">
            <Decision label="优先目标" value="回答质量 > 可解释性 > 成本" />
            <Decision label="淘汰原因" value="调研型 Agent 与当前任务主目标重叠较低" />
            <Decision label="用户控制" value="可以手动替换正式回答者" />
          </div>
        </Panel>
      </div>
    </WorkbenchShell>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}

function Decision({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}
