import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Play, RotateCcw, CheckCircle2, AlertCircle, Zap, GitBranch, Info } from "lucide-react";

const SAMPLE_FACTS = `involves(沪一中民五知初字第47号, 200480001590.4)
classified_in(200480001590.4, H04Q)`;

const SAMPLE_RULE = `IF involves(?J, ?P) AND classified_in(?P, ?IPC) THEN relates_to(?J, ?IPC)`;

// 领域模板：前 3 条为「图谱连接推理」（在现有关系上推出新边），
// 后 3 条为「法律要件推理」（输入案件事实推法律结论）。
// 注意：变量必须用 ? 前缀（如 ?J），否则推理引擎会把它当字面常量。
const TEMPLATES = [
  {
    labelKey: "reasoning.tplJudgmentIPC",
    facts: `involves(沪一中民五知初字第47号, 200480001590.4)\nclassified_in(200480001590.4, H04Q)`,
    rule: `IF involves(?J, ?P) AND classified_in(?P, ?IPC) THEN relates_to(?J, ?IPC)`,
  },
  {
    labelKey: "reasoning.tplTraceStatute",
    facts: `based_on(4W113883, 第九十三条)\nhas_article(中华人民共和国立法法, 第九十三条)`,
    rule: `IF based_on(?D, ?A) AND has_article(?L, ?A) THEN applies_statute(?D, ?L)`,
  },
  {
    labelKey: "reasoning.tplCurrentBasis",
    facts: `based_on(〔2008〕民三终字第10号, 专利法2008第二十二条)\nhas_article(中华人民共和国专利法2008, 专利法2008第二十二条)\nsupersedes(中华人民共和国专利法2020, 中华人民共和国专利法2008)`,
    rule: `IF based_on(?J, ?A) AND has_article(?O, ?A) AND supersedes(?N, ?O) THEN current_basis(?J, ?N)`,
  },
  {
    labelKey: "reasoning.tplInventive",
    facts: `closest_prior_art(对比文件1)\ndistinguishing_feature(对比文件1, 双轴驱动)\nno_technical_hint(双轴驱动)`,
    rule: `IF closest_prior_art(?D) AND distinguishing_feature(?D, ?F) AND no_technical_hint(?F) THEN inventive(?D)`,
  },
  {
    labelKey: "reasoning.tplNovelty",
    facts: `discloses(对比文件1, 特征A)\nclaimed(CN202011111111.1, 特征A)`,
    rule: `IF discloses(?D, ?F) AND claimed(?P, ?F) THEN anticipation(?P, ?D)`,
  },
  {
    labelKey: "reasoning.tplEquivalent",
    facts: `claim_means(权利要求1, 焊接)\nproduct_means(被控产品, 螺栓)\nsubstantially_same(焊接, 螺栓)`,
    rule: `IF claim_means(?C, ?M1) AND product_means(?X, ?M2) AND substantially_same(?M1, ?M2) THEN equivalent_infringe(?X, ?C)`,
  },
];

export function ReasoningWorkspace() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [facts, setFacts] = useState(SAMPLE_FACTS);
  const [rules, setRules] = useState(SAMPLE_RULE);
  const [applyToGraph, setApplyToGraph] = useState(true);
  const [result, setResult] = useState<{
    inferred_facts?: string[];
    rules_fired?: number;
    added_edges?: number;
    mutated?: boolean;
  } | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");

  async function handleRun() {
    setIsRunning(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/reason", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          facts: facts.split(/\r?\n/).map((l) => l.trim()).filter(Boolean),
          rules: rules.split(/\r?\n/).map((l) => l.trim()).filter(Boolean),
          mode: "forward",
          apply_to_graph: applyToGraph,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `Status ${response.status}`);
      if (response.status === 207) setError(data.message || t("reasoning.partialWarning"));
      setResult(data);
      if (data.mutated) queryClient.invalidateQueries({ queryKey: ["graph", "full-load"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("reasoning.failed"));
    } finally {
      setIsRunning(false);
    }
  }

  function loadTemplate(tpl: (typeof TEMPLATES)[number]) {
    setFacts(tpl.facts);
    setRules(tpl.rule);
    setResult(null);
    setError("");
  }

  function handleReset() {
    setFacts(SAMPLE_FACTS);
    setRules(SAMPLE_RULE);
    setResult(null);
    setError("");
  }

  return (
    <div className="ws-page" style={{ flexDirection: "row" }}>
      {/* ── Left: Input panel ── */}
      <div style={{ width: 480, flexShrink: 0, display: "flex", flexDirection: "column", borderRight: "1px solid var(--ws-border)", overflow: "hidden" }}>
        {/* Header */}
        <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 2 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "var(--ws-accent-soft)", border: "1px solid var(--ws-border-strong)", display: "grid", placeItems: "center", color: "var(--ws-accent)", flexShrink: 0 }}>
              <BrainCircuit size={16} />
            </div>
            <div>
              <div className="ws-eyebrow" style={{ marginBottom: 2 }}>{t("reasoning.forwardChaining")}</div>
              <div style={{ color: "var(--ws-text)", fontWeight: 700, fontSize: 15, lineHeight: 1 }}>{t("reasoning.inferenceEngine")}</div>
            </div>
          </div>
        </div>

        {/* Templates */}
        <div style={{ padding: "12px 16px 10px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0 }}>
          <div className="ws-eyebrow" style={{ marginBottom: 8 }}>{t("reasoning.quickTemplates")}</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {TEMPLATES.map((tpl) => (
              <button key={tpl.labelKey} className="ws-btn ws-btn--ghost" style={{ padding: "5px 10px", fontSize: 11 }} onClick={() => loadTemplate(tpl)}>
                {t(tpl.labelKey)}
              </button>
            ))}
          </div>
        </div>

        {/* Input area */}
        <div className="ws-scroll ws-padded" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="ws-label">{t("reasoning.facts")}</label>
            <div className="ws-body" style={{ marginBottom: 8 }}>{t("reasoning.factsHint1")}<code style={{ color: "var(--ws-accent)", fontSize: 11 }}>predicate(subject, object)</code>{t("reasoning.factsHint2")}</div>
            <textarea
              className="ws-textarea"
              value={facts}
              onChange={(e) => setFacts(e.target.value)}
              rows={6}
              spellCheck={false}
            />
          </div>

          <div>
            <label className="ws-label">{t("reasoning.rules")}</label>
            <div className="ws-body" style={{ marginBottom: 8 }}>{t("reasoning.rulesHint1")}<code style={{ color: "var(--ws-amber)", fontSize: 11 }}>IF … AND … THEN …</code> {t("reasoning.rulesHint2")}</div>
            <textarea
              className="ws-textarea"
              value={rules}
              onChange={(e) => setRules(e.target.value)}
              rows={5}
              spellCheck={false}
            />
          </div>

          {/* Apply toggle */}
          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "10px 12px", borderRadius: "var(--ws-radius-sm)", border: "1px solid var(--ws-border)", background: applyToGraph ? "var(--ws-green-soft)" : "var(--ws-surface)" }}>
            <div style={{ position: "relative", width: 36, height: 20, flexShrink: 0 }}>
              <input
                type="checkbox"
                checked={applyToGraph}
                onChange={(e) => setApplyToGraph(e.target.checked)}
                style={{ opacity: 0, position: "absolute", inset: 0, cursor: "pointer", margin: 0 }}
              />
              <div style={{ position: "absolute", inset: 0, borderRadius: 999, background: applyToGraph ? "var(--ws-green)" : "rgba(255,255,255,0.12)", transition: "background 180ms ease" }} />
              <div style={{ position: "absolute", top: 3, left: applyToGraph ? 19 : 3, width: 14, height: 14, borderRadius: 999, background: "#fff", transition: "left 180ms ease", boxShadow: "0 1px 4px rgba(0,0,0,0.4)" }} />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: applyToGraph ? "#6ee7b7" : "var(--ws-text-muted)" }}>{t("reasoning.applyToGraph")}</div>
              <div style={{ fontSize: 11, color: "var(--ws-text-dim)" }}>{t("reasoning.applyToGraphHint")}</div>
            </div>
          </label>

          {/* Actions */}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="ws-btn ws-btn--primary"
              onClick={handleRun}
              disabled={isRunning}
              style={{ flex: 1, justifyContent: "center" }}
            >
              {isRunning
                ? <><span className="ws-spin" style={{ display: "inline-block" }}><Zap size={15} /></span>{t("reasoning.running")}</>
                : <><Play size={14} />{t("reasoning.runReasoning")}</>}
            </button>
            <button className="ws-btn ws-btn--ghost" onClick={handleReset} title={t("reasoning.resetDefaults")}>
              <RotateCcw size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Right: Results panel ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "18px 24px 14px", borderBottom: "1px solid var(--ws-border)", flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ws-text)" }}>{t("reasoning.results")}</div>
          {result && !isRunning && (
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              <span className="ws-pill ws-pill--accent">
                <Zap size={9} /> {t("reasoning.rulesFired", { count: result.rules_fired ?? 0 })}
              </span>
              <span className="ws-pill ws-pill--green">
                <GitBranch size={9} /> {t("reasoning.edgesAdded", { count: result.added_edges ?? 0 })}
              </span>
              {result.mutated
                ? <span className="ws-pill ws-pill--green">{t("reasoning.graphUpdated")}</span>
                : <span className="ws-pill ws-pill--mono">{t("reasoning.previewOnly")}</span>}
            </div>
          )}
        </div>

        <div className="ws-scroll ws-padded" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {error && (
            <div className="ws-animate-in" style={{ display: "flex", gap: 10, padding: "12px 14px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-red-soft)", border: "1px solid rgba(255,123,114,0.28)", color: "#fca5a5", fontSize: 13 }}>
              <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <div>{error}</div>
            </div>
          )}

          {isRunning && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[1,2,3,4].map((i) => <div key={i} className="ws-skeleton" style={{ height: 52 }} />)}
            </div>
          )}

          {result && !isRunning && (
            <div className="ws-animate-in">
              {(result.inferred_facts ?? []).length === 0 ? (
                <div className="ws-empty">
                  <div className="ws-empty-icon"><CheckCircle2 size={32} /></div>
                  <div className="ws-empty-title">{t("reasoning.complete")}</div>
                  <div className="ws-empty-body">{t("reasoning.noNewFacts")}</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {result.inferred_facts!.map((fact, i) => (
                    <div key={`${fact}-${i}`} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", borderRadius: "var(--ws-radius-sm)", background: "var(--ws-surface)", border: "1px solid var(--ws-border)" }}>
                      <div style={{ width: 20, height: 20, borderRadius: 6, background: "var(--ws-green-soft)", border: "1px solid rgba(76,195,138,0.28)", display: "grid", placeItems: "center", flexShrink: 0, marginTop: 1 }}>
                        <CheckCircle2 size={11} color="var(--ws-green)" />
                      </div>
                      <code style={{ fontFamily: "'JetBrains Mono','Fira Code',monospace", fontSize: 12, color: "var(--ws-text)", lineHeight: 1.6, wordBreak: "break-all" }}>{fact}</code>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!result && !isRunning && !error && (
            <div className="ws-empty">
              <div className="ws-empty-icon"><Info size={32} /></div>
              <div className="ws-empty-title">{t("reasoning.ready")}</div>
              <div className="ws-empty-body">{t("reasoning.readyBody")}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
