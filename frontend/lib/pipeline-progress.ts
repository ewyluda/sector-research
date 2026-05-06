export const PHASE_ORDER = [
  "quick_screen",
  "deep_dive",
  "targeted_followup",
  "thesis_construction",
  "risk_stress_test",
  "position_monitor",
] as const;

export const PHASE_LABELS: Record<string, string> = {
  quick_screen: "Quick Screen",
  deep_dive: "Deep Dive",
  targeted_followup: "Targeted Follow-up",
  thesis_construction: "Thesis Construction",
  risk_stress_test: "Risk Stress-Test",
  position_monitor: "Position Monitor",
};

export const PHASE_ETA_SECONDS: Record<string, number> = {
  quick_screen: 30,
  deep_dive: 120,
  targeted_followup: 30,
  thesis_construction: 45,
  risk_stress_test: 45,
  position_monitor: 30,
};
