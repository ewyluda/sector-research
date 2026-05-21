import { ProspectusList } from "@/components/prospectus/ProspectusList";

export const dynamic = "force-dynamic";

export default function ProspectusIndexPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-semibold text-[var(--text)]">Prospectus Reports</h1>
          <p className="text-[var(--text-muted)] text-sm mt-2">
            Analytical reports synthesised from S-1 / S-1/A registrations.
          </p>
        </div>
        <ProspectusList />
      </div>
    </div>
  );
}
