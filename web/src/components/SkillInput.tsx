"use client";
import { useEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { api, fallback } from "@/lib/api";
export type Chip = { input: string; canonical: string | null };
type VocabEntry = { canonical: string; postings_mentioning: number | null };
export default function SkillInput({
  value,
  onChange,
  onSubmit,
  busy = false,
}: {
  value: Chip[];
  onChange: (v: Chip[]) => void;
  onSubmit?: () => void;
  busy?: boolean;
}) {
  const [text, setText] = useState("");
  const [vocab, setVocab] = useState<VocabEntry[]>(
    fallback.vocabulary.map((s) => ({ canonical: s, postings_mentioning: null })),
  );
  useEffect(() => {
    api
      .vocabulary()
      .then((r) => setVocab(r.skills))
      .catch(() => {
        /* FALLBACK: keeps the control testable without the API. */
      });
  }, []);
  const suggestions = text
    ? vocab
        .filter(
          (s) =>
            s.canonical.toLowerCase().includes(text.toLowerCase()) &&
            !value.some((v) => v.canonical === s.canonical),
        )
        .sort((a, b) => (b.postings_mentioning ?? 0) - (a.postings_mentioning ?? 0))
        .slice(0, 5)
    : [];
  async function commit(raw = text) {
    const input = raw.trim();
    if (!input) return;
    let canonical: string | null = null;
    try {
      canonical = (await api.normalize([input]))[0]?.canonical ?? null;
    } catch {
      /* FALLBACK: local vocabulary resolution keeps this control testable without the API. */ canonical =
        vocab.find((s) => s.canonical.toLowerCase() === input.toLowerCase())
          ?.canonical ?? null;
    }
    onChange([...value, { input, canonical }]);
    setText("");
  }
  return (
    <div>
      <div className="input-wrap">
        {value.map((v, i) => (
          <span
            key={`${v.input}-${i}`}
            title={
              v.canonical
                ? `${v.input} normalised to ${v.canonical}`
                : "Not in the job-posting vocabulary"
            }
            className={v.canonical ? "chip" : "chip unknown"}
          >
            {v.canonical ?? v.input}
            <button
              aria-label={`Remove ${v.input}`}
              onClick={() => onChange(value.filter((_, j) => j !== i))}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        <div className="typing">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commit();
              }
            }}
            placeholder={
              value.length ? "Add another skill" : "Type your skills…"
            }
          />
          {suggestions.length > 0 && (
            <div className="suggestions">
              {suggestions.map((s) => (
                <button
                  key={s.canonical}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => void commit(s.canonical)}
                >
                  <span>{s.canonical}</span>
                  {s.postings_mentioning != null && (
                    <small>{s.postings_mentioning.toLocaleString()}</small>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
        {onSubmit && (
          <button
            className="submit"
            aria-label="Get recommendations"
            disabled={busy || !value.length}
            onClick={onSubmit}
          >
            <ArrowRight size={21} />
          </button>
        )}
      </div>
      <style jsx>{`
        .input-wrap {
          min-height: 66px;
          border: 1px solid var(--ink);
          background: var(--paper);
          display: flex;
          align-items: center;
          gap: 7px;
          padding: 9px;
          position: relative;
          flex-wrap: wrap;
        }
        .chip {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          background: #dbe6f2;
          color: var(--graph);
          padding: 5px 8px;
          border-radius: 2px;
          font-size: 14px;
          animation: chip 0.15s ease;
        }
        .chip.unknown {
          background: var(--wash);
          color: var(--quiet);
          text-decoration: line-through;
        }
        .chip button {
          border: 0;
          background: none;
          color: inherit;
          padding: 0;
          display: flex;
        }
        .typing {
          position: relative;
          flex: 1;
          min-width: 140px;
        }
        .typing input {
          border: 0;
          outline: 0;
          background: transparent;
          width: 100%;
          padding: 7px;
        }
        .submit {
          border: 0;
          background: var(--graph);
          color: white;
          width: 46px;
          height: 46px;
          display: grid;
          place-items: center;
        }
        .submit:disabled {
          opacity: 0.4;
        }
        .suggestions {
          position: absolute;
          top: 48px;
          left: -10px;
          width: min(310px, 80vw);
          background: var(--paper);
          border: 1px solid var(--ink);
          z-index: 10;
        }
        .suggestions button {
          width: 100%;
          border: 0;
          border-bottom: 1px solid var(--rule);
          background: none;
          padding: 9px 12px;
          display: flex;
          justify-content: space-between;
        }
        .suggestions small {
          color: var(--quiet);
        }
        @keyframes chip {
          from {
            opacity: 0;
            transform: scale(0.9);
          }
        }
      `}</style>
    </div>
  );
}
