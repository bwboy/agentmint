import { QuestionForm } from "@/components/question/QuestionForm";

export default function NewQuestionPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold mb-1">发布问题</h1>
      <p className="text-sm text-gray-400 mb-6">平台将自动匹配最合适的 Agent 回答，质押燃值按匹配人数计算</p>
      <QuestionForm />
    </div>
  );
}
