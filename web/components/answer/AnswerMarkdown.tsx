import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseAnswerContent } from "./AnswerMarkdown.logic";

function TableWrapper({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto my-4">{children}</div>;
}

export function AnswerMarkdown({ text }: { text: string }) {
  const parsed = parseAnswerContent(text);
  return (
    <div className="space-y-3">
      {parsed.hasFinalAnswer ? (
        <div className="answer-body prose prose-sm max-w-none">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => (
                <TableWrapper>
                  <table className="answer-table">{children}</table>
                </TableWrapper>
              ),
              th: ({ children }) => <th className="answer-th">{children}</th>,
              td: ({ children }) => <td className="answer-td">{children}</td>,
            }}
          >
            {parsed.finalText}
          </ReactMarkdown>
        </div>
      ) : (
        <div className="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {parsed.workingOnly ? "Agent 仍在处理，本条暂未形成最终回答。" : "暂无可展示的最终回答。"}
        </div>
      )}
      {parsed.traces.length > 0 && (
        <details className="rounded-lg border border-border-subtle bg-bg-subtle/60 px-3 py-2 text-xs text-text-secondary">
          <summary className="cursor-pointer font-medium text-text-secondary hover:text-brand">
            运行过程记录 · {parsed.traces.length} 条
          </summary>
          <div className="mt-2 space-y-1.5">
            {parsed.traces.map((trace, index) => (
              <p key={`${trace.kind}-${index}`} className="break-all rounded-md bg-elevated px-2 py-1 font-mono text-[11px] text-text-tertiary">
                {trace.text}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
