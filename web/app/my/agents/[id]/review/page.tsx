import { ReviewQueue } from "@/components/review/ReviewQueue";

export default function ReviewPage({ params }: { params: { id: string } }) {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold mb-1">审核队列</h1>
      <p className="text-sm text-gray-400 mb-6">通过的回答会发布给提问者；拒绝则丢弃。</p>
      <ReviewQueue agentId={params.id} />
    </div>
  );
}
