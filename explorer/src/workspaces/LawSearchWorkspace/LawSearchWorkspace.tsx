import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Gavel, Landmark, ListTree, LoaderCircle, Search } from "lucide-react";

type Mode = "law" | "decision" | "judgment" | "ipc";

type Hit = {
  score: number;
  [key: string]: unknown;
};

type IpcNode = {
  code: string;
  title: string;
  level: string;
  decision_count: number;
  patent_count: number;
  has_children: boolean;
};

type IpcDecisionHit = {
  decision_id: string;
  case_number?: string;
  case_type?: string;
  decision_result?: string;
  decision_points?: string;
  application_number?: string;
  invention_name?: string;
  source_path?: string;
  source_file?: string;
  ipc?: string;
};

export function LawSearchWorkspace() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("law");
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
      const endpoint =
        mode === "decision" ? "/api/cnlaw/search/decisions"
        : mode === "judgment" ? "/api/cnlaw/search/judgments"
        : "/api/cnlaw/search";
      const response = await fetch(`${endpoint}?q=${encodeURIComponent(q)}&k=8`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Status ${response.status}`);
      setHits(data.results || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: Mode) {
    if (next === mode) return;
    setMode(next);
    setHits([]);
    setError("");
    setQuery("");
  }

  const modeButton = (m: Mode, label: string, icon: React.ReactNode) => (
    <button
      onClick={() => switchMode(m)}
      data-active={mode === m}
      style={{
        display: "flex", alignItems: "center", gap: 6, padding: "7px 14px",
        borderRadius: 8, border: "1px solid var(--ws-border)",
        background: mode === m ? "var(--ws-accent-soft)" : "var(--ws-surface)",
        color: mode === m ? "var(--ws-accent)" : "var(--ws-text-muted)",
        cursor: "pointer", fontSize: 13, fontWeight: 600,
      }}
    >
      {icon} {label}
    </button>
  );

  return (
    <div style={{ padding: 24, color: "var(--ws-text)" }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {modeButton("law", t("lawSearch.modeLaw"), <FileText size={14} />)}
        {modeButton("decision", t("lawSearch.modeDecision"), <Gavel size={14} />)}
        {modeButton("judgment", t("lawSearch.modeJudgment"), <Landmark size={14} />)}
        {modeButton("ipc", t("lawSearch.modeIpc"), <ListTree size={14} />)}
      </div>

      {mode === "ipc" ? (
        <IpcBrowser t={t} />
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              placeholder={
                mode === "decision" ? t("lawSearch.placeholderDecision")
                : mode === "judgment" ? t("lawSearch.placeholderJudgment")
                : t("lawSearch.placeholder")
              }
              style={{
                flex: 1, padding: "10px 12px", borderRadius: 8,
                border: "1px solid var(--ws-border)", background: "var(--ws-surface)", color: "var(--ws-text)",
              }}
            />
            <button
              onClick={runSearch}
              disabled={loading}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "10px 16px",
                borderRadius: 8, border: "1px solid var(--ws-border-strong)",
                background: "var(--ws-accent-soft)", color: "var(--ws-accent)", cursor: "pointer",
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

          {mode === "law"
            ? hits.map((h, i) => <LawCard key={i} h={h} />)
            : mode === "decision"
            ? hits.map((h, i) => <DecisionCard key={i} h={h} />)
            : hits.map((h, i) => <JudgmentCard key={i} h={h} />)}
        </>
      )}
    </div>
  );
}

// ── IPC classification browser ───────────────────────────────────────────────

function IpcBrowser({ t }: { t: (k: string) => string }) {
  const [sections, setSections] = useState<IpcNode[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [selected, setSelected] = useState<IpcNode | null>(null);
  const [decisions, setDecisions] = useState<IpcDecisionHit[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [choice, setChoice] = useState("");

  async function loadSections() {
    setLoadState("loading");
    try {
      const resp = await fetch("/api/cnlaw/ipc/sections");
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `Status ${resp.status}`);
      setSections(data || []);
      setLoadState("ready");
    } catch (e) {
      setLoadState("error");
    }
  }

  useEffect(() => {
    loadSections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function pick(node: IpcNode) {
    setSelected(node);
    setChoice(node.code);
    setListLoading(true);
    setDecisions([]);
    try {
      const resp = await fetch(`/api/cnlaw/ipc/${encodeURIComponent(node.code)}/decisions?k=50`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `Status ${resp.status}`);
      setDecisions(data.results || []);
    } finally {
      setListLoading(false);
    }
  }

  if (loadState === "loading" && sections.length === 0) {
    return <div style={{ color: "var(--ws-text-muted)" }}>{t("common.loading")}</div>;
  }
  if (loadState === "error") {
    return (
      <div style={{ color: "var(--warm)" }}>
        {t("lawSearch.error")}
        <button onClick={loadSections} style={{ marginLeft: 8, cursor: "pointer" }}>{t("lawSearch.button")}</button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 320px", maxWidth: 520 }}>
          {sections.map((s) => <IpcTreeNode key={s.code} node={s} depth={0} onSelect={pick} selectedCode={choice} />)}
        </div>
        <div style={{ flex: "1 1 480px", minWidth: 0 }}>
          <div style={{ color: "var(--ws-text-muted)", fontSize: 13, marginBottom: 8 }}>
            {selected ? `${selected.code} ${selected.title}`.trim() : t("lawSearch.ipcHint")}
          </div>
          {listLoading && <div style={{ color: "var(--ws-text-muted)" }}>{t("common.loading")}</div>}
          {!listLoading && selected && decisions.length === 0 && (
            <div style={{ color: "var(--ws-text-muted)" }}>{t("lawSearch.ipcEmpty")}</div>
          )}
          {decisions.map((d, i) => <DecisionCard key={i} h={{ ...d, score: 0 } as Hit} />)}
        </div>
      </div>
    </div>
  );
}

function IpcTreeNode({ node, depth, onSelect, selectedCode }: {
  node: IpcNode;
  depth: number;
  onSelect: (n: IpcNode) => void;
  selectedCode: string;
}) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<IpcNode[] | null>(null);
  const [loading, setLoading] = useState(false);
  const isSelected = selectedCode === node.code;

  async function toggle() {
    if (!open && node.has_children && children === null) {
      setLoading(true);
      try {
        const resp = await fetch(`/api/cnlaw/ipc/tree?parent=${encodeURIComponent(node.code)}`);
        const data = await resp.json();
        setChildren(data || []);
        setOpen(true);
      } finally {
        setLoading(false);
      }
    } else {
      setOpen(!open);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", paddingLeft: depth * 18, gap: 4 }}>
        {node.has_children ? (
          <button onClick={toggle} style={{ background: "none", border: "none", cursor: "pointer", padding: 2, color: "var(--ws-text-muted)" }}>
            {loading ? <LoaderCircle size={13} /> : open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        ) : (
          <span style={{ width: 17 }} />
        )}
        <button
          onClick={() => onSelect(node)}
          data-active={isSelected}
          style={{
            background: "none", border: "none", cursor: "pointer", padding: "3px 6px",
            borderRadius: 6, textAlign: "left", fontSize: 13,
            color: isSelected ? "var(--ws-accent)" : "var(--ws-text)",
            fontWeight: isSelected ? 700 : 500,
          }}
        >
          <span style={{ color: "var(--ws-accent)", fontFamily: "monospace" }}>{node.code}</span>
          {node.title && <span style={{ marginLeft: 6 }}>{node.title}</span>}
          <span style={{ color: "var(--ws-text-muted)", marginLeft: 8, fontSize: 12 }}>{node.decision_count}</span>
        </button>
      </div>
      {open && children && children.map((c) => (
        <IpcTreeNode key={c.code} node={c} depth={depth + 1} onSelect={onSelect} selectedCode={selectedCode} />
      ))}
    </div>
  );
}

// ── Cards ────────────────────────────────────────────────────────────────────

const cardShell: React.CSSProperties = {
  padding: "12px 14px", marginBottom: 10, borderRadius: 8,
  border: "1px solid var(--ws-border)", background: "var(--ws-surface)",
};

function LawCard({ h }: { h: Hit }) {
  const full_name = h.full_name as string;
  const number = h.number as string;
  const text = h.text as string;
  const status = h.status as string;
  const domain = h.domain as string;
  const category = h.category as string;
  const source_path = h.source_path as string;
  const source_date = h.source_date as string;
  return (
    <div style={cardShell}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <span style={{ color: "var(--ws-accent)", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <FileText size={14} /> {full_name} · {number}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ws-text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
          {(h.score as number).toFixed(3)}
          {domain && (
            <span style={{ padding: "1px 6px", borderRadius: 6, border: "1px solid var(--ws-border-strong)", background: "var(--ws-accent-soft)", color: "var(--ws-accent)" }}>{domain}</span>
          )}
          {category && category !== domain && (
            <span style={{ padding: "1px 6px", borderRadius: 6, border: "1px solid var(--ws-border-strong)", background: "var(--ws-accent-soft)", color: "var(--ws-accent)" }}>{category}</span>
          )}
          · {status}
        </span>
      </div>
      <div style={{ color: "var(--ws-text-muted)", fontSize: 13, lineHeight: 1.55 }}>{text}</div>
      <div style={{ color: "var(--ws-text-muted)", fontSize: 12, marginTop: 6, wordBreak: "break-all" }}>
        溯源：{source_path || full_name} · {source_date} · {status}
      </div>
    </div>
  );
}

function DecisionCard({ h }: { h: Hit }) {
  const invention_name = h.invention_name as string;
  const decision_id = h.decision_id as string;
  const case_number = h.case_number as string;
  const case_type = h.case_type as string;
  const decision_result = h.decision_result as string;
  const decision_points = h.decision_points as string;
  const application_number = h.application_number as string;
  const source_path = h.source_path as string;
  const ipc = h.ipc as string;
  return (
    <div style={cardShell}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <span style={{ color: "var(--ws-accent)", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <Gavel size={14} /> {invention_name || decision_id}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ws-text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
          {(h.score as number).toFixed(3)}
          {ipc && (
            <span style={{ padding: "1px 6px", borderRadius: 6, border: "1px solid var(--ws-border-strong)", background: "var(--ws-accent-soft)", color: "var(--ws-accent)", fontFamily: "monospace" }}>{ipc}</span>
          )}
          {case_type && (
            <span style={{ padding: "1px 6px", borderRadius: 6, border: "1px solid var(--ws-border-strong)", background: "var(--ws-accent-soft)", color: "var(--ws-accent)" }}>{case_type}</span>
          )}
          · {decision_result}
        </span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>决定号：{decision_id}</span>
        {case_number && <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>案件号：{case_number}</span>}
        {application_number && <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>专利号：{application_number}</span>}
      </div>
      {decision_points && (
        <div style={{ color: "var(--ws-text-muted)", fontSize: 13, lineHeight: 1.55 }}>{decision_points}</div>
      )}
      <div style={{ color: "var(--ws-text-muted)", fontSize: 12, marginTop: 6, wordBreak: "break-all" }}>
        溯源：{source_path || decision_id}
      </div>
    </div>
  );
}

function JudgmentCard({ h }: { h: Hit }) {
  const judgment_id = h.judgment_id as string;
  const case_number = h.case_number as string;
  const case_type = h.case_type as string;
  const cause = h.cause as string;
  const court = h.court as string;
  const decision_result = h.decision_result as string;
  const invention_name = h.invention_name as string;
  const application_number = h.application_number as string;
  const source_path = h.source_path as string;
  const title = invention_name || cause || judgment_id;
  return (
    <div style={cardShell}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
        <span style={{ color: "var(--ws-accent)", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <Landmark size={14} /> {title}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ws-text-muted)", fontSize: 12, whiteSpace: "nowrap" }}>
          {(h.score as number).toFixed(3)}
          {case_type && (
            <span style={{ padding: "1px 6px", borderRadius: 6, border: "1px solid var(--ws-border-strong)", background: "var(--ws-accent-soft)", color: "var(--ws-accent)" }}>{case_type}</span>
          )}
          · {decision_result}
        </span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        {case_number && <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>案号：{case_number}</span>}
        {court && <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>法院：{court}</span>}
        {application_number && <span style={{ fontSize: 12, color: "var(--ws-text-muted)" }}>专利号：{application_number}</span>}
      </div>
      {cause && (
        <div style={{ color: "var(--ws-text-muted)", fontSize: 13, lineHeight: 1.55 }}>{cause}</div>
      )}
      <div style={{ color: "var(--ws-text-muted)", fontSize: 12, marginTop: 6, wordBreak: "break-all" }}>
        溯源：{source_path || judgment_id}
      </div>
    </div>
  );
}
