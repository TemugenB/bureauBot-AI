import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";

type FlagCategory = "wrong_info" | "outdated" | "incomplete" | "other";

const REASONS: { value: FlagCategory; label: string; description: string }[] = [
  { value: "wrong_info", label: "Wrong information", description: "The answer contains factual errors." },
  { value: "outdated", label: "Outdated", description: "The information is no longer current." },
  { value: "incomplete", label: "Incomplete", description: "Important details are missing." },
  { value: "other", label: "Other", description: "Something else." },
];

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  turnId: number;
  onFlagged: () => void;
};

export function FlagMessageDialog({ open, onOpenChange, sessionId, turnId, onFlagged }: Props) {
  const [reason, setReason] = useState<FlagCategory | null>(null);
  const [_details, setDetails] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setReason(null);
    setDetails("");
    setSubmitting(false);
    setSuccess(false);
    setError(null);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) setTimeout(reset, 200);
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    if (!reason) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/chat/flag", { session_id: sessionId, turn_id: turnId, category: reason });
      setSuccess(true);
      onFlagged();
      setTimeout(() => handleOpenChange(false), 1200);
    } catch (err) {
      setError(err instanceof ApiError ? `Couldn't submit (${err.status}).` : "Network error.");
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Report this answer</DialogTitle>
          <DialogDescription>Help us improve. What's wrong with this response?</DialogDescription>
        </DialogHeader>

        {success ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Check className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-foreground">Thanks for the feedback</p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {REASONS.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setReason(r.value)}
                  className={[
                    "w-full rounded-md border p-3 text-left transition-colors",
                    reason === r.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/40 hover:bg-accent/40",
                  ].join(" ")}
                >
                  <div className="text-sm font-medium text-foreground">{r.label}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{r.description}</div>
                </button>
              ))}
            </div>

            {reason === "other" && (
              <Textarea onChange={(e) => setDetails(e.target.value)} placeholder="Tell us more (optional)" className="min-h-[80px]" />
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <DialogFooter>
              <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={submitting}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={!reason || submitting}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Submit report
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
