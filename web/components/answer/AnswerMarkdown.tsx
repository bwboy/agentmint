import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function TableWrapper({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto my-4">{children}</div>;
}

export function AnswerMarkdown({ text }: { text: string }) {
  return (
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
        {text || ""}
      </ReactMarkdown>
    </div>
  );
}
