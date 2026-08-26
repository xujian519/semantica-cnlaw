import i18n from "../../i18n";
import type { GraphLoadPhase, GraphLoadProgress, GraphLoadProgressKind, GraphLayoutSource, GraphLayoutState } from "./types";

export const GRAPH_LOAD_STAGE_SEQUENCE: Exclude<GraphLoadPhase, "ready">[] = [
  "bootstrapping",
  "fetching_nodes",
  "fetching_edges",
  "computing_styling",
  "hydrating_scene",
  "stabilizing_layout",
];

export function getGraphLoadTitle(phase: GraphLoadPhase): string {
  switch (phase) {
    case "bootstrapping":
      return i18n.t("graphLoading.titlePreparing");
    case "fetching_nodes":
      return i18n.t("graphLoading.titleLoadingNodes");
    case "fetching_edges":
      return i18n.t("graphLoading.titleLoadingRelationships");
    case "computing_styling":
      return i18n.t("graphLoading.titleStyling");
    case "hydrating_scene":
      return i18n.t("graphLoading.titleHydrating");
    case "stabilizing_layout":
      return i18n.t("graphLoading.titleStabilizing");
    case "ready":
    default:
      return i18n.t("graphLoading.titleReady");
  }
}

export function getGraphLoadStageLabel(phase: Exclude<GraphLoadPhase, "ready">): string {
  switch (phase) {
    case "bootstrapping":
      return i18n.t("graphLoading.stagePrepare");
    case "fetching_nodes":
      return i18n.t("graphLoading.stageNodes");
    case "fetching_edges":
      return i18n.t("graphLoading.stageRelations");
    case "computing_styling":
      return i18n.t("graphLoading.stageStyling");
    case "hydrating_scene":
      return i18n.t("graphLoading.stageScene");
    case "stabilizing_layout":
      return i18n.t("graphLoading.stageLayout");
    default:
      return i18n.t("graphLoading.stageFallback");
  }
}

export function createGraphLoadProgress(input: {
  phase: GraphLoadPhase;
  message: string;
  progressKind: GraphLoadProgressKind;
  loaded?: number | null;
  total?: number | null;
  nodesLoaded?: number;
  nodesTotal?: number | null;
  edgesLoaded?: number;
  edgesTotal?: number | null;
  showGraphBehind?: boolean;
  layoutSource?: GraphLayoutSource;
  layoutState?: GraphLayoutState;
}): GraphLoadProgress {
  const phaseIndex = GRAPH_LOAD_STAGE_SEQUENCE.indexOf(input.phase as Exclude<GraphLoadPhase, "ready">);

  return {
    phase: input.phase,
    title: getGraphLoadTitle(input.phase),
    message: input.message,
    progressKind: input.progressKind,
    loaded: input.loaded ?? null,
    total: input.total ?? null,
    nodesLoaded: input.nodesLoaded ?? 0,
    nodesTotal: input.nodesTotal ?? null,
    edgesLoaded: input.edgesLoaded ?? 0,
    edgesTotal: input.edgesTotal ?? null,
    showGraphBehind: input.showGraphBehind ?? false,
    stageIndex: phaseIndex >= 0 ? phaseIndex + 1 : GRAPH_LOAD_STAGE_SEQUENCE.length,
    stageCount: GRAPH_LOAD_STAGE_SEQUENCE.length,
    layoutSource: input.layoutSource,
    layoutState: input.layoutState,
  };
}
