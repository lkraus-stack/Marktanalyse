import Link from "next/link";

export default function HomePage() {
  return (
    <section className="flex min-h-[50vh] items-center justify-center">
      <Link
        href="/dashboard"
        className="rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
      >
        Zum Dashboard
      </Link>
    </section>
  );
}
