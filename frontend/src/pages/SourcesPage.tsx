import { useEffect, useState } from "react";
import { Container } from "@/components/Container";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

type DocumentInfo = { id: string; title: string; jurisdiction: string; task_category: string | null; ingested_at: string };

export function SourcesPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<DocumentInfo[]>("/documents")
      .then(setDocuments)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <Container className="py-10">
      <h1 className="text-3xl font-bold tracking-tight text-foreground">Sources</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        Official documents and references the Navigator draws from.
      </p>

      <div className="mt-8">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : documents.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            No sources loaded yet.
          </div>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
                <div>
                  <h3 className="font-medium text-foreground">{doc.title}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Added {new Date(doc.ingested_at).toLocaleDateString()}
                    {doc.task_category && ` · ${doc.task_category}`}
                  </p>
                </div>
                <Badge variant="secondary">{doc.jurisdiction}</Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    </Container>
  );
}
