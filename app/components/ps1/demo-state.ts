export const demoSteps = ["Dataset", "Scenario", "Optimisation", "Validation", "Objective", "Export"] as const;
export type DemoStep = (typeof demoSteps)[number];

export const scenarioDescriptions = {
  A: ["Minimise priority-weighted completion overrun.", "ECLO forbidden.", "Capacity excess forbidden."],
  B: ["Meet planned completion dates.", "ECLO and capacity excess carry penalties."],
  C: ["Balance delay, ECLO and capacity excess.", "One excess unit maximum per location/week.", "Separate Alpha and Beta ECLO windows."],
} as const;

export const solverPresets = {
  Quick: { time_limit_seconds: 5, deterministic_time_limit: 2, random_seed: 0 },
  Balanced: { time_limit_seconds: 20, deterministic_time_limit: 10, random_seed: 0 },
  Thorough: { time_limit_seconds: 120, deterministic_time_limit: 60, random_seed: 0 },
} as const;

export type PublicationInput = {
  candidate: boolean;
  feasible: boolean;
  physicalComplete: boolean;
  hardViolations: number | null;
  backendAccepted: boolean;
};

export function publicationGate(input: PublicationInput) {
  const checks = [
    { label: "Candidate exists", passed: input.candidate, reason: "No candidate schedule exists." },
    { label: "Schedule feasible", passed: input.feasible, reason: "The schedule has not passed feasibility validation." },
    { label: "Physical validation complete", passed: input.physicalComplete, reason: "Physical-night validation is incomplete." },
    { label: "Zero hard violations", passed: input.hardViolations === 0, reason: input.hardViolations === null ? "Hard violations have not been checked." : `${input.hardViolations} hard violation(s) remain.` },
    { label: "CSV export permitted", passed: input.backendAccepted, reason: "The backend has not accepted CSV publication." },
  ];
  return { checks, eligible: checks.every(check => check.passed), reason: checks.filter(check => !check.passed).map(check => check.reason).join(" ") };
}

export function solverExplanation(status: string) {
  switch (status) {
    case "OPTIMAL": return "An optimal schedule was proven for the configured model.";
    case "FEASIBLE": return "A feasible schedule was found; optimality was not proven.";
    case "UNKNOWN": return "No schedule was found or disproved within the configured search limit.";
    case "INFEASIBLE": return "The solver proved that no schedule satisfies these constraints.";
    case "MODEL_INVALID": return "The solver rejected the optimisation model.";
    case "VALIDATOR_REJECTED":
    case "VALIDATION_FAILED": return "A candidate was rejected by the internal validator.";
    default: return "Review the solver diagnostics for this outcome.";
  }
}
