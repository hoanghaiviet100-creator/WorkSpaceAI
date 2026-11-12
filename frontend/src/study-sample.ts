import type { StudyItem, StudyKind, StudySet } from "./study-model";

const facts = [
  [
    "Computational thinking",
    "How does decomposition help solve complex problems?",
    "Decomposition breaks a complex problem into smaller, manageable parts.",
    [
      "Break the problem into smaller parts",
      "Combine every step into one",
      "Ignore error cases",
      "Rename the problem",
    ],
  ],
  [
    "Computational thinking",
    "What does pattern recognition help you reuse?",
    "Pattern recognition finds similarities so existing solutions can be reused.",
    ["A new dataset", "A known solution", "A variable name", "A random result"],
  ],
  [
    "Computational thinking",
    "What information does abstraction retain?",
    "Abstraction retains the details relevant to the current goal.",
    [
      "Every detail",
      "Only the document name",
      "Relevant details",
      "The first detail encountered",
    ],
  ],
  [
    "Algorithms",
    "What must an algorithm describe?",
    "An algorithm is a finite sequence of well-defined steps for solving a problem.",
    [
      "An arbitrary list",
      "A single result",
      "An unlimited dataset",
      "A finite sequence of steps",
    ],
  ],
  [
    "Algorithms",
    "What does time complexity describe?",
    "Time complexity describes how execution cost grows with input size.",
    [
      "Execution cost as a function of input size",
      "Time spent writing code",
      "Available disk space",
      "Number of application users",
    ],
  ],
  [
    "Algorithms",
    "What condition must the data meet for binary search?",
    "Binary search requires sorted data so it can discard half of the search range at each step.",
  ],
  [
    "Testing",
    "Why should you test boundary values?",
    "Boundary-value testing catches errors where conditions change, such as at the beginning or end of a range.",
  ],
  [
    "Testing",
    "What does a test case need to check an actual result?",
    "A test case provides input and an expected result to compare with the actual result.",
  ],
] as const;
const correct = [0, 1, 2, 3, 0];
const sampleSource = "study-sample-computational-thinking";

export function sampleStudy(kind: StudyKind): StudySet {
  const items: StudyItem[] = facts
    .slice(0, kind === "quiz" ? 5 : 8)
    .map(([topic, question, answer, options], index) => ({
      id: `sample-${index}`,
      topic,
      question,
      answer,
      citation: {
        docId: sampleSource,
        file: "Computational thinking · sample document",
        page: 1,
        startLine: index + 1,
        endLine: index + 1,
        quote: answer,
      },
      ...(kind === "quiz"
        ? { options: [...options!], correctIndex: correct[index] }
        : {}),
    }));
  return {
    id: `sample-${kind}`,
    title:
      kind === "quiz"
        ? "Computational thinking quiz"
        : "Computational thinking fundamentals",
    createdAt: new Date().toISOString(),
    status: "ready",
    engine: "sample",
    config: {
      kind,
      sourceIds: [sampleSource],
      count: items.length,
      difficulty: "medium",
      focus: "",
    },
    items,
  };
}
