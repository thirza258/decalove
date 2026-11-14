/**
 * A coarse, local reading of what a menu option is asking the player to do.
 *
 * The engine already guarantees the options differ. This is presentation: a small tag
 * helps the player scan a menu instead of re-reading four sentences to find the one
 * that is a question rather than a confession. It never decides anything and never
 * rewrites the option text.
 */

export type ChoiceIntent =
  | "support"
  | "challenge"
  | "ask"
  | "feeling"
  | "observe"
  | "strategy"
  | "other";

export interface ChoiceIntentStyle {
  key: ChoiceIntent;
  label: string;
  /** A single glyph, used at the end of the option. */
  glyph: string;
  className: string;
}

const STYLES: Record<ChoiceIntent, Omit<ChoiceIntentStyle, "key">> = {
  support: {
    label: "Support",
    glyph: "♥",
    className: "border-emerald-300/25 bg-emerald-300/10 text-emerald-200/90",
  },
  challenge: {
    label: "Challenge",
    glyph: "!",
    className: "border-rose-300/25 bg-rose-300/10 text-rose-200/90",
  },
  ask: {
    label: "Ask",
    glyph: "?",
    className: "border-sky-300/25 bg-sky-300/10 text-sky-200/90",
  },
  feeling: {
    label: "Feeling",
    glyph: "~",
    className: "border-violet-300/25 bg-violet-300/10 text-violet-200/90",
  },
  observe: {
    label: "Observe",
    glyph: "·",
    className: "border-slate-300/20 bg-slate-300/10 text-slate-200/80",
  },
  strategy: {
    label: "Strategy",
    glyph: "◆",
    className: "border-amber-300/25 bg-amber-300/10 text-amber-200/90",
  },
  other: {
    label: "Choice",
    glyph: "›",
    className: "border-white/15 bg-white/5 text-white/60",
  },
};

const RULES: { key: ChoiceIntent; pattern: RegExp }[] = [
  {
    key: "feeling",
    pattern:
      /\b(?:love|adore|feel(?:ings)?|confess|sorry|apolog|forgive|miss you|need you|cry|hug|kiss|blush|afraid|scared)\b/i,
  },
  {
    key: "challenge",
    pattern:
      /\b(?:confront|accuse|challenge|demand|refuse|call (?:her|him|them) out|angry|furious|argue|fight|push back|not fair|how dare|no\b)\b/i,
  },
  {
    key: "ask",
    pattern:
      /\b(?:ask|question|find out|investigate|press|why|what happened|who|tell me|explain|clarify|look (?:for|into))\b/i,
  },
  {
    key: "support",
    pattern:
      /\b(?:help|support|comfort|reassure|listen|be there|protect|defend|stay (?:with|by)|i'?m here|take your time|it'?s okay)\b/i,
  },
  {
    key: "strategy",
    pattern:
      /\b(?:lie|deceive|negotiate|bargain|distract|threaten|promise|trade|bribe|change the subject|deflect|pretend|keep it secret)\b/i,
  },
  {
    key: "observe",
    pattern:
      /\b(?:say nothing|wait|observe|watch|leave|walk away|nod|shrug|do nothing|stay silent|let the moment|give (?:her|him|them) (?:a )?(?:moment|space))\b/i,
  },
];

export function classifyChoice(text: string): ChoiceIntentStyle {
  const key = RULES.find((rule) => rule.pattern.test(text))?.key ?? "other";
  return { key, ...STYLES[key] };
}
