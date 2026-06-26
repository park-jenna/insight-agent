export type WorkspaceSource = {
  id: string;
  group: "documents" | "datasets";
  name: string;
  format: "PDF" | "CSV";
  count: number;
  countLabel: "chunks" | "rows";
  status: "indexed" | "synced";
};

export type WorkspaceMetrics = {
  policyDocuments: number;
  indexedPassages: number;
  enrollmentRecords: number;
};

export type WorkspaceFilters = {
  scope: "all" | "documents" | "data";
  program: "any" | "ELEVATE" | "IMPACT";
  status: "any" | "Active" | "Inactive" | "Completed";
  keyword: string;
};

export type ExampleQuestionCategory = {
  id: string;
  label: string;
  tone: "green" | "rust" | "blue" | "purple";
  questions: Array<{ label: string; query: string }>;
};

export type TraceStep = {
  tool: string;
  args: Record<string, unknown>;
  result?: Record<string, unknown>;
  ms?: number;
};

export type AgentSource = {
  filename: string;
  type: string;
  passages: number;
};

export type AgentRun = {
  trace: TraceStep[];
  latency: number;
  steps: number;
  sources: AgentSource[];
  completedAt?: Date;
};

export type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  run?: AgentRun;
  streaming?: boolean;
};

export type EvidenceItem = {
  id: string;
  label: string;
  detail: string;
  chips: string[];
  active: boolean;
};

export const DEFAULT_FILTERS: WorkspaceFilters = {
  scope: "all",
  program: "any",
  status: "any",
  keyword: "",
};

export const WORKSPACE_SOURCES: WorkspaceSource[] = [
  {
    id: "illinois-special-education-administrative-code",
    group: "documents",
    name: "IL Admin Code Part 226",
    format: "PDF",
    count: 331,
    countLabel: "chunks",
    status: "indexed",
  },
  {
    id: "special-education-consent-form-instructions",
    group: "documents",
    name: "Consent form instructions",
    format: "PDF",
    count: 116,
    countLabel: "chunks",
    status: "indexed",
  },
  {
    id: "student-enrollment",
    group: "datasets",
    name: "Student enrollment",
    format: "CSV",
    count: 300,
    countLabel: "rows",
    status: "synced",
  },
];

export const WORKSPACE_METRICS: WorkspaceMetrics = {
  policyDocuments: WORKSPACE_SOURCES.filter(
    (source) => source.group === "documents",
  ).length,
  indexedPassages: WORKSPACE_SOURCES.filter(
    (source) => source.group === "documents",
  ).reduce((total, source) => total + source.count, 0),
  enrollmentRecords:
    WORKSPACE_SOURCES.find((source) => source.group === "datasets")?.count ?? 0,
};

export const EXAMPLE_QUESTION_CATEGORIES: ExampleQuestionCategory[] = [
  {
    id: "policy",
    label: "Policy questions",
    tone: "green",
    questions: [
      {
        label: "How does a parent file a state complaint?",
        query:
          "How does a parent file a state complaint about special education?",
      },
      {
        label: "What notice is required before consent?",
        query: "What notice is required before requesting parent consent?",
      },
    ],
  },
  {
    id: "student-records",
    label: "Student records",
    tone: "rust",
    questions: [
      {
        label: "How many students are active vs inactive?",
        query: "How many students are active versus inactive?",
      },
      {
        label: "Which programs have the most inactive?",
        query: "Which programs have the highest number of inactive students?",
      },
    ],
  },
  {
    id: "program-insights",
    label: "Program insights",
    tone: "blue",
    questions: [
      {
        label: "What % of students are in ELEVATE?",
        query: "What percentage of students are in the ELEVATE program?",
      },
      {
        label: "How many grade 12 students are enrolled?",
        query: "How many grade 12 students are enrolled?",
      },
    ],
  },
  {
    id: "trends",
    label: "Trends",
    tone: "purple",
    questions: [
      {
        label: "Show the monthly enrollment trend.",
        query: "Show the monthly enrollment trend.",
      },
      {
        label: "How have enrollments changed since June 2025?",
        query: "How have enrollments changed since June 2025?",
      },
    ],
  },
];

export const SUGGESTED_QUESTIONS = [
  {
    label: "Parent complaint process",
    query: "How does a parent file a state complaint about special education?",
  },
  {
    label: "Active vs inactive",
    query: "How many students are active versus inactive?",
  },
  {
    label: "Monthly enrollment trend",
    query: "Show the monthly enrollment trend.",
  },
  {
    label: "ELEVATE breakdown",
    query: "What percentage of students are in the ELEVATE program?",
  },
];
