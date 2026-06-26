import type {
  AgentRun,
  EvidenceItem,
  TraceStep,
} from "@/app/workspace";

function text(value: unknown, fallback = "") {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : fallback;
}

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function array(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

export function describeStep(step: TraceStep): string {
  const args = step.args ?? {};
  switch (step.tool) {
    case "search_documents":
      return "Searched the policy documents";
    case "analyze_dataset":
      return "Looked up the student records";
    case "detect_trends":
      return "Tracked enrollment over time";
    case "find_anomalies":
      return "Checked the dataset for unusual values";
    case "calculate_ratios":
      return "Calculated a share from the student records";
    case "compare_periods":
      return "Compared two enrollment periods";
    default:
      return text(args.label, step.tool.replaceAll("_", " "));
  }
}

export function describeStepDetail(step: TraceStep): string {
  const args = step.args ?? {};
  const result = step.result ?? {};
  if (result.error) return text(result.error);

  switch (step.tool) {
    case "search_documents": {
      const results = array(result.results);
      const sourceCount = new Set(results.map((item) => item.source)).size;
      return `Retrieved ${results.length} passage${
        results.length === 1 ? "" : "s"
      } from ${sourceCount} document${sourceCount === 1 ? "" : "s"}.`;
    }
    case "analyze_dataset": {
      const values = object(result.top_values);
      if (Object.keys(values).length > 0) {
        return `Grouped ${Object.values(values).reduce<number>(
          (sum, value) => sum + Number(value || 0),
          0,
        )} records by ${text(args.column, "the selected field")}.`;
      }
      if (result.row_count) {
        return `Inspected ${text(result.row_count)} records in ${text(
          args.dataset_name,
          "the dataset",
        )}.`;
      }
      return `Analyzed ${text(args.dataset_name, "the dataset")}.`;
    }
    case "detect_trends":
      return `Grouped ${array(result.points).length} periods using ${text(
        args.date_column,
        "the date field",
      )}.`;
    case "find_anomalies":
      return `Found ${text(result.outlier_count, "0")} outliers in ${text(
        args.column,
        "the selected field",
      )}.`;
    case "calculate_ratios":
      return `Calculated ${text(result.percentage, "the requested")}% from the selected records.`;
    case "compare_periods":
      return `Compared records around ${text(args.split_date, "the selected date")}.`;
    default:
      return "Completed this analysis step.";
  }
}

export function evidenceFromRun(run?: AgentRun): EvidenceItem[] {
  if (!run) return [];
  return run.trace.map((step, index) => {
    const chips = [
      step.tool === "search_documents" ? "source: PDF" : "source: data",
      step.ms != null ? `${step.ms} ms` : "",
    ].filter(Boolean);

    if (step.args.column) chips.push(`group: ${text(step.args.column)}`);
    if (step.args.date_column) {
      chips.push(`date: ${text(step.args.date_column)}`);
    }

    return {
      id: step.tool === "search_documents" ? `P${index + 1}` : `D${index + 1}`,
      label: describeStep(step),
      detail: describeStepDetail(step),
      chips,
      active: !step.result?.error,
    };
  });
}

export function answerTitle(run?: AgentRun) {
  const trace = run?.trace ?? [];
  const trend = trace.find((step) => step.tool === "detect_trends");
  if (trend) return "Enrollment trend";

  const categorical = trace.find(
    (step) =>
      step.tool === "analyze_dataset" &&
      object(step.result?.top_values) &&
      Object.keys(object(step.result?.top_values)).length > 0,
  );
  if (categorical) {
    return `${text(categorical.args.column, "Record")} breakdown`;
  }

  if (trace.some((step) => step.tool === "search_documents")) {
    return "Policy guidance";
  }
  return "Workspace answer";
}

export function technicalStep(step: TraceStep) {
  const args = Object.entries(step.args ?? {})
    .map(([key, value]) => `${key}: ${text(value)}`)
    .join(" · ");
  return args ? `${step.tool} · ${args}` : step.tool;
}

export type ResultTable = {
  headings: string[];
  rows: string[][];
};

export function resultTable(run?: AgentRun): ResultTable | null {
  const trace = run?.trace ?? [];

  for (const step of trace) {
    const result = step.result ?? {};
    const values = object(result.top_values);
    if (Object.keys(values).length > 0) {
      const total = Object.values(values).reduce<number>(
        (sum, value) => sum + Number(value || 0),
        0,
      );
      return {
        headings: [text(step.args.column, "Category"), "Records", "Share"],
        rows: Object.entries(values).map(([label, value]) => [
          label,
          String(value),
          total ? `${((Number(value) / total) * 100).toFixed(1)}%` : "—",
        ]),
      };
    }

    const points = array(result.points);
    if (points.length > 0) {
      const valueKey =
        Object.keys(points[0]).find((key) => key !== "period") ?? "count";
      return {
        headings: ["Period", valueKey.replaceAll("_", " ")],
        rows: points.map((point) => [
          text(point.period),
          text(point[valueKey]),
        ]),
      };
    }
  }

  return null;
}

export function renderBoldText(content: string) {
  return content.split("**").map((part, index) =>
    index % 2 === 1 ? <strong key={index}>{part}</strong> : part,
  );
}
