import type { SimulationState, TagAlias } from "@/types/simulation";

/** Display tag (reference HMI numbering) of an engineering tag; the
 * engineering tag itself when no alias is configured. */
export function displayTag(state: Pick<SimulationState, "tag_aliases">, tag: string): string {
  return state.tag_aliases?.[tag]?.tag ?? tag;
}

export function aliasOf(state: Pick<SimulationState, "tag_aliases">, tag: string): TagAlias | null {
  return state.tag_aliases?.[tag] ?? null;
}

export const ALIAS_STATUS_LABEL: Record<TagAlias["status"], string> = {
  verified: "Tag read from the reference",
  uncertain: "Tag partly legible on the reference - verify against the P&ID",
  placeholder: "Placeholder tag - not shown on the reference",
  addition: "SubseaSim addition - not on the reference page",
};

/** Replace engineering tags in free text (event messages) with display tags. */
export function aliasText(state: Pick<SimulationState, "tag_aliases">, text: string): string {
  const a = state.tag_aliases;
  if (!a) return text;
  return text.replace(/[A-Z]{2,5}-[A-Z0-9-]*d+/g, (t) => (a[t] && a[t].tag !== t ? a[t].tag : t));
}
