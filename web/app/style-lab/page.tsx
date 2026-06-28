import Link from "next/link";

const styles = [
  {
    href: "/style-lab/a",
    key: "A",
    title: "Clean AI Workbench",
    desc: "克制、专业、工具感强。适合作为正式产品长期使用。",
    bg: "bg-[#f7f9fc]",
    accent: "text-cyan-600",
  },
  {
    href: "/style-lab/b",
    key: "B",
    title: "Dark Agent Arena",
    desc: "竞技、选角、对抗感更强。突出 Agent 能力差异。",
    bg: "bg-[#090b10]",
    accent: "text-lime-300",
  },
  {
    href: "/style-lab/c",
    key: "C",
    title: "Futuristic Glass Console",
    desc: "更像 AI 概念控制台，适合 demo 感和视觉冲击。",
    bg: "bg-[#eef4ff]",
    accent: "text-blue-600",
  },
];

const matchingModes = [
  {
    href: "/style-lab/matching/a",
    key: "A",
    title: "智能路由型",
    desc: "平台直接选出推荐阵容，弱化过程，用户最快进入答案。",
    meta: "Auto Route",
  },
  {
    href: "/style-lab/matching/b",
    key: "B",
    title: "选角透明型",
    desc: "展示领域、能力、历史表现和成本信号，突出为什么选这些 Agent。",
    meta: "Casting Board",
  },
  {
    href: "/style-lab/matching/c",
    key: "C",
    title: "试镜竞标型",
    desc: "候选 Agent 先给计划、信心、报价，再选择正式回答者。",
    meta: "Audition",
  },
];

export default function StyleLabPage() {
  return (
    <div className="min-h-[calc(100vh-160px)] bg-[#f4f6f9] px-4 py-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400">Style Lab</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">AgentMint 匹配模式 demo</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
            当前先统一采用 Clean AI Workbench 风格。下面三个页面分别测试智能路由、选角透明、试镜竞标三种 Agent 匹配方式。
          </p>
        </div>

        <div className="mb-10 grid gap-4 md:grid-cols-3">
          {matchingModes.map(item => (
            <Link
              key={item.key}
              href={item.href}
              className="group rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-lg"
            >
              <div className="flex items-center justify-between">
                <span className="grid size-9 place-items-center rounded-full bg-slate-950 text-sm font-semibold text-white">{item.key}</span>
                <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700">{item.meta}</span>
              </div>
              <h2 className="mt-5 font-semibold text-slate-950">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">{item.desc}</p>
              <span className="mt-4 inline-flex text-sm font-medium text-cyan-600">查看匹配 demo</span>
            </Link>
          ))}
        </div>

        <div className="mb-4 border-t border-slate-200 pt-8">
          <h2 className="text-sm font-semibold text-slate-900">早期风格参考</h2>
          <p className="mt-1 text-sm text-slate-500">这三个页面先保留，后续可以重新做真正差异化的风格探索。</p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {styles.map(item => (
            <Link
              key={item.key}
              href={item.href}
              className="group overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-lg"
            >
              <div className={`h-36 ${item.bg} p-4`}>
                <div className="flex h-full flex-col justify-between rounded-md border border-white/40 bg-white/20 p-4">
                  <div className={`text-sm font-semibold ${item.accent}`}>Style {item.key}</div>
                  <div className="space-y-2">
                    <div className="h-2 w-28 rounded-full bg-current opacity-30" />
                    <div className="h-2 w-40 rounded-full bg-current opacity-20" />
                    <div className="h-2 w-20 rounded-full bg-current opacity-20" />
                  </div>
                </div>
              </div>
              <div className="p-5">
                <h2 className="font-semibold text-slate-950">{item.title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">{item.desc}</p>
                <span className="mt-4 inline-flex text-sm font-medium text-cyan-600">查看 demo</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
