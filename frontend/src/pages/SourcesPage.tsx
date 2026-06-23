import { useEffect, useState } from "react";
import { Container } from "@/components/Container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, isAdmin } from "@/lib/api";
import { Star, X, Loader2 } from "lucide-react";

type DocumentInfo = { id: string; title: string; jurisdiction: string; task_category: string | null; featured: boolean; ingested_at: string };
type PreviewDoc = { filename: string; source_url: string; content: string; is_pdf: boolean; warning: string | null };

export function SourcesPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"documents" | "add" | "flags">("documents");
  const [error, setError] = useState("");
  const admin = isAdmin();

  const fetchDocs = () => {
    setError("");
    api.get<DocumentInfo[]>("/documents")
      .then(setDocuments)
      .catch((err: any) => setError(err?.message || "Failed to load documents"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDocs(); }, []);

  const toggleFeatured = async (doc: DocumentInfo) => {
    try {
      await api.patch(`/documents/${doc.id}/featured`, { featured: !doc.featured });
      setDocuments((prev) => prev.map((d) => d.id === doc.id ? { ...d, featured: !d.featured } : d));
    } catch (err: any) { setError(err?.message || "Failed to update featured status"); }
  };

  const loadDemo = async () => {
    try {
      await api.post("/demo/load");
      fetchDocs();
    } catch (err: any) { setError(err?.message || "Failed to load demo data"); }
  };

  return (
    <Container className="py-10">
      <h1 className="text-3xl font-bold tracking-tight text-foreground">Sources</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        Official documents and references the assistant draws from.
      </p>

      {admin && (
        <div className="mt-6 flex gap-2 border-b border-border">
          <button onClick={() => setTab("documents")} className={`px-4 py-2 text-sm font-medium ${tab === "documents" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}>Documents</button>
          <button onClick={() => setTab("add")} className={`px-4 py-2 text-sm font-medium ${tab === "add" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}>Add Sources</button>
          <button onClick={() => setTab("flags")} className={`px-4 py-2 text-sm font-medium ${tab === "flags" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}>Flags</button>
        </div>
      )}

      <div className="mt-8">
        {error && (
          <div className="mb-4 rounded-md border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            ⚠ {error}
          </div>
        )}
        {tab === "documents" && (
          <DocumentsTab documents={documents} setDocuments={setDocuments} loading={loading} admin={admin} onToggleFeatured={toggleFeatured} onLoadDemo={loadDemo} />
        )}
        {tab === "add" && admin && (
          <AddSourcesTab onIngested={fetchDocs} />
        )}
        {tab === "flags" && admin && (
          <FlagsTab />
        )}
      </div>
    </Container>
  );
}

function DocumentsTab({ documents, setDocuments, loading, admin, onToggleFeatured, onLoadDemo }: {
  documents: DocumentInfo[]; setDocuments: React.Dispatch<React.SetStateAction<DocumentInfo[]>>; loading: boolean; admin: boolean;
  onToggleFeatured: (doc: DocumentInfo) => void; onLoadDemo: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedContent, setExpandedContent] = useState<string>("");
  const [loadingContent, setLoadingContent] = useState(false);

  const startRename = (doc: DocumentInfo) => {
    setEditingId(doc.id);
    setEditTitle(doc.title);
  };

  const saveRename = async (doc: DocumentInfo) => {
    if (editTitle.trim() && editTitle !== doc.title) {
      await api.patch(`/documents/${doc.id}/title`, { title: editTitle.trim() });
      setDocuments((prev) => prev.map((d) => d.id === doc.id ? { ...d, title: editTitle.trim() } : d));
    }
    setEditingId(null);
  };

  const toggleExpand = async (doc: DocumentInfo) => {
    if (expandedId === doc.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(doc.id);
    setLoadingContent(true);
    try {
      const res = await api.get<{ content: string }>(`/documents/${doc.id}/content`);
      setExpandedContent(res.content);
    } catch { setExpandedContent("Failed to load content."); }
    setLoadingContent(false);
  };

  if (loading) return <p className="text-sm text-muted-foreground">Loading...</p>;

  if (documents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        <p>No sources loaded yet.</p>
        {admin && <Button onClick={onLoadDemo} className="mt-4">💡 Load Demo Data</Button>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {documents.map((doc) => (
        <div key={doc.id} className="rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between p-4 cursor-pointer" onClick={() => toggleExpand(doc)}>
            <div>
              {editingId === doc.id ? (
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} className="h-8 text-sm" onKeyDown={(e) => { if (e.key === "Enter") saveRename(doc); if (e.key === "Escape") setEditingId(null); }} autoFocus />
                  <Button size="sm" variant="ghost" onClick={() => saveRename(doc)}>Save</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                </div>
              ) : (
                <h3 className="font-medium text-foreground" onDoubleClick={(e) => { e.stopPropagation(); admin && startRename(doc); }}>{doc.title}</h3>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                Added {new Date(doc.ingested_at).toLocaleDateString()}
                {doc.task_category && ` · ${doc.task_category}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {admin && (
                <>
                  <button onClick={(e) => { e.stopPropagation(); onToggleFeatured(doc); }} className={`p-1 rounded ${doc.featured ? "text-yellow-500" : "text-muted-foreground hover:text-yellow-500"}`} title={doc.featured ? "Remove from featured" : "Add to featured"}>
                    <Star className={`h-4 w-4 ${doc.featured ? "fill-yellow-500" : ""}`} />
                  </button>
                  <button onClick={async (e) => { e.stopPropagation(); if (confirm("Delete this document?")) { await api.delete(`/documents/${doc.id}`); setDocuments((prev) => prev.filter((d) => d.id !== doc.id)); } }} className="p-1 rounded text-muted-foreground hover:text-red-500" title="Delete document">
                    <X className="h-4 w-4" />
                  </button>
                </>
              )}
              <Badge variant="secondary">{doc.jurisdiction}</Badge>
            </div>
          </div>
          {expandedId === doc.id && (
            <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground whitespace-pre-wrap max-h-64 overflow-y-auto">
              {loadingContent ? "Loading..." : expandedContent}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function AddSourcesTab({ onIngested }: { onIngested: () => void }) {
  return (
    <div className="space-y-10">
      <CrawlSection onIngested={onIngested} />
      <PasteSection onIngested={onIngested} />
    </div>
  );
}

function CrawlSection({ onIngested }: { onIngested: () => void }) {
  const [urls, setUrls] = useState("");
  const [domains, setDomains] = useState("");
  const [previews, setPreviews] = useState<PreviewDoc[]>([]);
  const [crawling, setCrawling] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState("");
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  const handleImport = async () => {
    const url = urls.trim();
    if (!url) return;
    const urlList = [url];
    const manualDomains = domains.split(",").map((d) => d.trim()).filter(Boolean);
    const urlDomains = urlList.map((u) => { try { return new URL(u).hostname; } catch { return ""; } }).filter(Boolean);
    const domainList = [...new Set([...urlDomains, ...manualDomains])];
    setCrawling(true);
    setError("");
    try {
      const res = await api.post<{ documents: PreviewDoc[] }>("/crawl/preview", { urls: urlList, allowed_domains: domainList });
      setPreviews(res.documents);
    } catch (err: any) { setError(err?.message || "Crawl failed"); }
    setCrawling(false);
  };

  const removePreview = (idx: number) => {
    setPreviews((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateContent = (idx: number, content: string) => {
    setPreviews((prev) => prev.map((p, i) => i === idx ? { ...p, content } : p));
  };

  const updateFilename = (idx: number, filename: string) => {
    setPreviews((prev) => prev.map((p, i) => i === idx ? { ...p, filename } : p));
  };

  const handleConfirm = async () => {
    const docs = previews.filter((p) => p.content.trim()).map((p) => ({
      title: p.filename.replace(/\.(txt|pdf)$/, "").replace(/[-_]/g, " "),
      content: p.content,
      source_url: p.source_url,
      jurisdiction: "HU",
      task_category: null,
    }));
    if (!docs.length) return;
    setIngesting(true);
    try {
      await api.post("/crawl/ingest", { documents: docs });
      setPreviews([]);
      setUrls("");
      setDomains("");
      onIngested();
    } catch (err: any) { setError(err?.message || "Ingest failed"); }
    setIngesting(false);
  };

  return (
    <section>
      <h2 className="text-lg font-semibold text-foreground">Import from URL</h2>
      {error && (
        <div className="mt-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          ⚠ {error}
        </div>
      )}
      <div className="mt-4 space-y-3">
        <div>
          <label className="text-sm font-medium text-foreground">URL</label>
          <Input value={urls} onChange={(e) => setUrls(e.target.value)} className="mt-1" placeholder="https://example.com/page" />
        </div>
        <div>
          <label className="text-sm font-medium text-foreground">Allowed domains (comma-separated, optional)</label>
          <Input value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="domain.com, other-site.org (no https://)" className="mt-1" />
        </div>
        <Button onClick={handleImport} disabled={crawling}>
          {crawling ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Importing...</> : "Import"}
        </Button>
      </div>

      {previews.length > 0 && (
        <div className="mt-6 space-y-4">
          <h3 className="text-sm font-semibold text-foreground">Preview ({previews.length} pages)</h3>
          {previews.map((p, i) => (
            <div key={i} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <div>
                  {editingIdx === i ? (
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="h-7 text-sm w-48"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") { updateFilename(i, editName); setEditingIdx(null); }
                        if (e.key === "Escape") setEditingIdx(null);
                      }}
                      autoFocus
                    />
                  ) : (
                    <span
                      className="text-sm font-medium cursor-pointer"
                      onDoubleClick={() => { setEditingIdx(i); setEditName(p.filename); }}
                    >
                      {p.filename}
                    </span>
                  )}
                  <span className="ml-2 text-xs text-muted-foreground">{p.source_url}</span>
                </div>
                <div className="flex items-center gap-2">
                  {p.warning && <Badge variant="outline" className="border-yellow-500 text-yellow-600">{p.warning}</Badge>}
                  <button onClick={() => removePreview(i)} className="text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
                </div>
              </div>
              <textarea value={p.content} onChange={(e) => updateContent(i, e.target.value)} rows={6} className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-xs font-mono" />
            </div>
          ))}
          <Button onClick={handleConfirm} disabled={ingesting}>
            {ingesting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</> : "Confirm"}
          </Button>
        </div>
      )}
    </section>
  );
}

function PasteSection({ onIngested }: { onIngested: () => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [jurisdiction, setJurisdiction] = useState("HU");
  const [category, setCategory] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!title.trim() || text.trim().length < 50) return;
    setSubmitting(true);
    setError("");
    try {
      await api.post("/ingest", { title, text, jurisdiction, task_category: category || null });
      setTitle(""); setText(""); setCategory("");
      onIngested();
    } catch (err: any) { setError(err?.message || "Ingest failed"); }
    setSubmitting(false);
  };

  return (
    <section>
      <h2 className="text-lg font-semibold text-foreground">Paste Manually</h2>
      {error && (
        <div className="mt-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          ⚠ {error}
        </div>
      )}
      <div className="mt-4 space-y-3">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Document title" />
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm" placeholder="Paste document content here (min 50 characters)..." />
        <div className="flex gap-3">
          <Input value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="Jurisdiction (e.g. HU)" className="w-24" />
          <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category (optional)" className="flex-1" />
        </div>
        <Button onClick={handleAdd} disabled={submitting}>
          {submitting ? "Adding..." : "Add"}
        </Button>
      </div>
    </section>
  );
}

type FlagInfo = { id: number; session_id: string | null; turn_id: number | null; category: string; created_at: string };

function FlagsTab() {
  const [flags, setFlags] = useState<FlagInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<FlagInfo[]>("/admin/flags")
      .then(setFlags)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-sm text-muted-foreground">Loading...</p>;

  if (flags.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No flags yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {flags.map((f) => (
        <div key={f.id} className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
          <div>
            <Badge variant="secondary">{f.category}</Badge>
            <p className="mt-1 text-xs text-muted-foreground">
              Session: {f.session_id?.slice(0, 8)}… · Turn: {f.turn_id} · {new Date(f.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
