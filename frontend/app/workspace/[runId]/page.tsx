import { WorkspaceReport } from "@/components/workspace/WorkspaceReport";

export default async function Page({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <WorkspaceReport runId={runId} />;
}
