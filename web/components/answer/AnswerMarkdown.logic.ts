export type AnswerRuntimeTrace = {
  kind: "tool" | "status";
  text: string;
};

export type ParsedAnswerContent = {
  finalText: string;
  traces: AnswerRuntimeTrace[];
  hasFinalAnswer: boolean;
  workingOnly: boolean;
};

const TOOL_TRACE_START_PATTERN = /(?:🌐\s*)?browser_[a-z_]+:|(?:💻\s*)?terminal:|(?:🧰\s*)?tool_[a-z_]+:|(?:👁️\s*)?vision_analyze:|(?:🖼️\s*)?image_analyze:/g;
const STATUS_LINE_PATTERN = /(?:⏳|⌛)?\s*(Working|Interrupting current task|Running|Thinking)\s*(?:—|-).*/i;

export function parseAnswerContent(text: string): ParsedAnswerContent {
  const traces: AnswerRuntimeTrace[] = [];
  const finalLines: string[] = [];

  for (const rawLine of String(text || "").split(/\r?\n/)) {
    let line = rawLine;
    const extracted = extractToolTraces(line);
    for (const trace of extracted.traces) traces.push({ kind: "tool", text: trace });
    line = extracted.text.trim();

    if (!line) {
      if (finalLines.length && finalLines[finalLines.length - 1] !== "") finalLines.push("");
      continue;
    }

    if (STATUS_LINE_PATTERN.test(line)) {
      traces.push({ kind: "status", text: line });
      continue;
    }

    finalLines.push(line);
  }

  const finalText = trimBlankLines(finalLines).join("\n");
  return {
    finalText,
    traces,
    hasFinalAnswer: finalText.trim().length > 0,
    workingOnly: !finalText.trim() && traces.some(trace => trace.kind === "status"),
  };
}

function extractToolTraces(line: string) {
  const starts = [...line.matchAll(TOOL_TRACE_START_PATTERN)].map(match => ({
    index: match.index || 0,
    value: match[0],
  }));
  if (!starts.length) return { text: line, traces: [] };

  const traces: string[] = [];
  let text = "";
  let cursor = 0;

  for (let index = 0; index < starts.length; index += 1) {
    const start = starts[index];
    const nextStart = starts[index + 1]?.index ?? line.length;

    text += line.slice(cursor, start.index);
    const trace = normalizeTrace(line.slice(start.index, nextStart));
    if (trace) traces.push(trace);
    cursor = nextStart;
  }
  text += line.slice(cursor);

  return { text, traces };
}

function normalizeTrace(value: string) {
  return value.replace(/^\s+/, "").trim();
}

function trimBlankLines(lines: string[]) {
  let start = 0;
  let end = lines.length;
  while (start < end && !lines[start].trim()) start += 1;
  while (end > start && !lines[end - 1].trim()) end -= 1;
  return lines.slice(start, end);
}
