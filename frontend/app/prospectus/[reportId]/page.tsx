import { ProspectusReportView } from "@/components/prospectus/ProspectusReport";

export default async function ProspectusReportPage(
  { params }: { params: Promise<{ reportId: string }> },
) {
  const { reportId } = await params;
  return <ProspectusReportView reportId={reportId} />;
}
