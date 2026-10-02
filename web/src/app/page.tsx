import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Kredpare</h1>
      <p className="text-muted-foreground max-w-md text-center text-sm">
        Daily reconciliation of files exchanged with counterparties. The case UI arrives in
        Iteration 8.
      </p>
      <Button variant="outline" disabled>
        No reconciliation runs yet
      </Button>
    </main>
  );
}
