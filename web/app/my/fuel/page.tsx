import { FuelLedgerPanel } from "@/components/billing/FuelLedgerPanel";
import { PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MyFuelPage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Fuel Ledger"
        title="燃值流水"
        description="查看提问预留、未投递退款和 Agent 回答收入。"
        compact
      />
      <FuelLedgerPanel />
    </PageShell>
  );
}
