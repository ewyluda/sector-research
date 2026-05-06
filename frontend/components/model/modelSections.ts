// frontend/components/model/modelSections.ts
export const MODEL_TABS = [
  { id: "forecast",    label: "Forecast",    hash: "#forecast" },
  { id: "reverse-dcf", label: "Reverse DCF", hash: "#reverse-dcf" },
  { id: "history",     label: "History",     hash: "#history" },
] as const;
export type ModelTab = (typeof MODEL_TABS)[number]["id"];
