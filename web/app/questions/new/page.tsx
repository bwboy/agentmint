import { QuestionForm } from "@/components/question/QuestionForm";

export default function NewQuestionPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Command</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">发起一次 Agent 调度</h1>
        <p className="mt-2 text-sm text-gray-500">
          先用自然语言描述任务，再用领域标签和回答人数控制智能路由与选角透明度。
        </p>
      </div>
      <QuestionForm />
    </div>
  );
}
