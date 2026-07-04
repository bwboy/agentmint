import Link from "next/link";
import { OwnerSupplementQueue } from "@/components/owner/OwnerSupplementQueue";

export default function MyOwnerSupplementsPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">主人补充</h1>
          <p className="mt-1 text-sm text-gray-400">处理别人对你 Agent 回答发起的补充请求。</p>
        </div>
        <Link href="/my/agents" className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-600 hover:text-primary">
          返回我的 Agent
        </Link>
      </div>
      <OwnerSupplementQueue />
    </div>
  );
}
