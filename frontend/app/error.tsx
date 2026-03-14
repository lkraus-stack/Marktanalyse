"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error("App error boundary", error);
  }, [error]);

  return (
    <section className="mx-auto flex min-h-[60vh] max-w-2xl items-center">
      <Card className="w-full border-red-500/40">
        <CardHeader>
          <CardTitle>Unerwarteter Fehler</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>Beim Laden der Seite ist ein Fehler aufgetreten. Bitte versuche es erneut.</p>
          <Button onClick={reset}>Erneut versuchen</Button>
        </CardContent>
      </Card>
    </section>
  );
}
