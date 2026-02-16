"use client";

import { useState, useCallback } from "react";
import { MessageSquareWarning, Loader2, CheckCircle2, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { ErrorBanner } from "@/components/shared/error-banner";
import { submitFeedback } from "@/services/graph.service";
import type { FeedbackResponse } from "@/types/admin.types";

export function FeedbackPanel() {
  const [naturalLanguage, setNaturalLanguage] = useState("");
  const [generatedSql, setGeneratedSql] = useState("");
  const [feedback, setFeedback] = useState("");
  const [correctedSql, setCorrectedSql] = useState("");
  const [rating, setRating] = useState(0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FeedbackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!naturalLanguage.trim() || !generatedSql.trim() || !feedback.trim())
      return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await submitFeedback({
          natural_language: naturalLanguage.trim(),
          generated_sql: generatedSql.trim(),
          feedback: feedback.trim(),
          rating: rating || null,
          corrected_sql: correctedSql.trim(),
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [naturalLanguage, generatedSql, feedback, rating, correctedSql]);

  const clearForm = useCallback(() => {
    setNaturalLanguage("");
    setGeneratedSql("");
    setFeedback("");
    setCorrectedSql("");
    setRating(0);
    setResult(null);
    setError(null);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">SQL Feedback</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Submit feedback on generated SQL to improve future results.
        </p>
      </div>

      <Card className="p-6 space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Natural Language Query
          </label>
          <Input
            value={naturalLanguage}
            onChange={(e) => setNaturalLanguage(e.target.value)}
            placeholder="What was the original question?"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Generated SQL
          </label>
          <Textarea
            value={generatedSql}
            onChange={(e) => setGeneratedSql(e.target.value)}
            placeholder="Paste the generated SQL here"
            className="font-mono text-sm"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">Feedback</label>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe what was wrong or right about the SQL"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Corrected SQL{" "}
            <span className="font-normal text-muted-foreground">
              (optional)
            </span>
          </label>
          <Textarea
            value={correctedSql}
            onChange={(e) => setCorrectedSql(e.target.value)}
            placeholder="Provide the correct SQL if applicable"
            className="font-mono text-sm"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">Rating</label>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRating(n === rating ? 0 : n)}
                className="rounded p-1 transition-colors hover:bg-accent"
              >
                <Star
                  className={`h-5 w-5 ${
                    n <= rating
                      ? "fill-yellow-400 text-yellow-400"
                      : "text-muted-foreground"
                  }`}
                />
              </button>
            ))}
            {rating > 0 && (
              <span className="ml-2 text-xs text-muted-foreground">
                {rating}/5
              </span>
            )}
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <Button
            onClick={handleSubmit}
            disabled={
              loading ||
              !naturalLanguage.trim() ||
              !generatedSql.trim() ||
              !feedback.trim()
            }
            className="gap-1.5"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <MessageSquareWarning className="h-4 w-4" />
            )}
            Submit Feedback
          </Button>
          <Button variant="outline" onClick={clearForm}>
            Clear
          </Button>
        </div>
      </Card>

      {error && <ErrorBanner message={error} />}

      {result && (
        <Card className="border-green-500/30 bg-green-500/5 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 text-green-600 dark:text-green-400" />
            <div>
              <p className="text-sm font-medium text-green-700 dark:text-green-300">
                Feedback submitted successfully
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Episode ID: {result.episode_id}
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
