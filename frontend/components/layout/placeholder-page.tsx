import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type PlaceholderPageProps = {
  title: string;
  description: string;
};

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">{title}</h2>
        <p className="text-sm text-slate-600">{description}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{title} Modul</CardTitle>
          <CardDescription>Platzhalter fuer Phase 1.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-slate-600">
          Dieser Bereich wird in den naechsten Phasen mit Daten, Analysen und Interaktionen ausgebaut.
        </CardContent>
      </Card>
    </section>
  );
}
