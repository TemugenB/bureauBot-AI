import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, ArrowRight, Search } from "lucide-react";
import { Container } from "@/components/Container";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

type DocumentInfo = { id: string; title: string; featured: boolean };

export function HomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [featured, setFeatured] = useState<DocumentInfo[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<DocumentInfo[]>("/documents")
      .then((docs) => setFeatured(docs.filter((d) => d.featured)))
      .catch((err: any) => setError(err?.message || "Failed to load"));
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (q) navigate(`/chat?q=${encodeURIComponent(q)}`);
  };

  return (
    <Container className="py-12 sm:py-20">
      <div className="mx-auto max-w-3xl text-center">
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
          What do you need help with?
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Pick a process below or describe your situation. We'll guide you step by step with answers backed by official sources.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. How do I renew my residence permit?" className="h-12 pl-10 text-base" />
          </div>
          <Button type="submit" size="lg" className="h-12 gap-2">
            Ask <ArrowRight className="h-4 w-4" />
          </Button>
        </form>
      </div>

      {error && (
        <div className="mt-6 rounded-md border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300 text-center">
          ⚠ {error}
        </div>
      )}

      {featured.length > 0 && (
        <div className="mt-14">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Popular processes</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {featured.map((doc) => (
              <Card
                key={doc.id}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/chat?topic=${encodeURIComponent(doc.title)}`)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate(`/chat?topic=${encodeURIComponent(doc.title)}`); } }}
                className="group cursor-pointer transition-all hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <CardContent className="flex items-start gap-4 p-5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-foreground">{doc.title}</h3>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </Container>
  );
}
