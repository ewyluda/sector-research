import { redirect } from "next/navigation";

export default async function ReportRedirectPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  redirect(`/pipeline/${runId}`);
}
