import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { IdCard, HeartPulse, GraduationCap, Home as HomeIcon, CreditCard, Banknote, ArrowRight, Search } from "lucide-react";
import { Container } from "@/components/Container";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Category = { slug: string; title: string; description: string; icon: React.ComponentType<{ className?: string }> };

const CATEGORIES: Category[] = [
  { slug: "residence-permit", title: "Residence Permit Renewal", description: "Online application, required documents, and Immigration Office visits.", icon: IdCard },
  { slug: "health-insurance", title: "Health Insurance", description: "TAJ card, private insurance, and travel insurance options.", icon: HeartPulse },
  { slug: "student-id", title: "Student ID", description: "Temporary student ID certificate via Neptun E066 request.", icon: GraduationCap },
  { slug: "address-card", title: "Address Card", description: "Change of accommodation notification on Enter Hungary.", icon: HomeIcon },
  { slug: "taj-card", title: "TAJ Card Application", description: "First TAJ application for scholarship holders at building R.", icon: CreditCard },
  { slug: "tax-id", title: "Tax ID", description: "When you need a tax ID and how to apply at the tax office.", icon: Banknote },
];

export function HomePage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

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

      <div className="mt-14">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Popular processes</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            return (
              <Card
                key={cat.slug}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/chat?category=${cat.slug}`)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate(`/chat?category=${cat.slug}`); } }}
                className="group cursor-pointer transition-all hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <CardContent className="flex items-start gap-4 p-5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-foreground">{cat.title}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{cat.description}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </Container>
  );
}
