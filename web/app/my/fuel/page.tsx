import { FuelLedgerPanel } from "@/components/billing/FuelLedgerPanel";

export default function MyFuelPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Fuel Ledger</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">燃值流水</h1>
        <p className="mt-2 text-sm text-gray-500">
          查看提问预留、未投递退款和 Agent 回答收入。
        </p>
      </div>
      <FuelLedgerPanel />
    </div>
  );
}
