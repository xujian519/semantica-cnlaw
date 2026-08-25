import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, LoaderCircle, Search } from "lucide-react";

type Hit = {
  full_name: string;
  source_date: string;
  number: string;
  text: string;
  status: string;
  domain: string;
  source_path: string;
  score: number;
};

export function LawSearchWorkspace() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runSearch() {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError("");
    setHits([]);
    try {
      const response = await fetch(`/api/cnlaw/search?q=${encodeURIComponent(q)}&k=8`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Status ${response.status}`);
      setHits(data.results || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: 24, color: "var(--ws-text)" }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runSearch();
          }}
          placeholder={t("lawSearch.placeholder")}
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid var(--ws-border)",
            background: "var(--ws-surface)",
            color: "var(--ws-text)",
          }}
        />
        <button
          onClick={runSearch}
          disabled={loading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "10px 16px",
            borderRadius: 8,
            border: "1px solid var(--ws-border-strong)",
            background: "var(--ws-accent-soft)",
            color: "var(--ws-accent)",
            cursor: "pointer",
          }}
        >
          {loading ? <LoaderCircle size={16} /> : <Search size={16} />}
          {t("lawSearch.button")}
        </button>
      </div>

      {error && (
        <div style={{ color: "var(--warm)", marginBottom: 12 }}>{t("lawSearch.error")}: {error}</div>
      )}

      {!loading && query && hits.length === 0 && !error && (
        <div style={{ color: "var(--ws-text-muted)" }}>{t("lawSearch.empty")}</div>
      )}

      {hits.map((h, i) => (
        <div
          key={i}
          style={{
            padding: "12px 14px",
            marginBottom: 10,
            borderRadius: 8,
            border: "1px solid var(--ws-border)",
            background: "var(--ws-surface)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
            <span style={{ color: "var(--ws-accent)", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <FileText size={14} />
              {h.full_name} · {h.number}
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ws-text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
              {h.score.toFixed(3)}
              {h.domain && (
                <span
                  style={{
                    padding: "1px 6px",
                    borderRadius: 6,
                    border: "1px solid var(--ws-border-strong)",
                    background: "var(--ws-accent-soft)",
                    color: "var(--ws-accent)",
                  }}
                >
                  {h.domain}
                </span>
              )}
              · {h.status}
            </span>
          </div>
          <div style={{ color: "var(--ws-text-muted)", fontSize: 13, lineHeight: 1.55 }}>{h.text}</div>
          <div style={{ color: "var(--ws-text-muted)", fontSize: 12, marginTop: 6, wordBreak: "break-all" }}>
            溯源：{h.source_path || h.full_name} · {h.source_date} · {h.status}
          </div>
        </div>
      ))}
    </div>
  );
}
