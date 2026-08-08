// HTML conformance and markup-level accessibility rules for the built pages.
//
// Where a rule is waived or tightened, the reason is here rather than in a commit
// message, because a waived rule with no reason beside it is indistinguishable from an
// oversight.
export default {
  extends: [
    "html-validate:recommended",
    "html-validate:document",
    "html-validate:a11y",
  ],
  rules: {
    // The bar segments carry a width computed from the counts they draw. That width is
    // data, not presentation, and there is no stylesheet that could hold one class per
    // possible percentage.
    "no-inline-style": "off",
    // The WHATWG spec writes the doctype lowercase and HTML5 is case-insensitive here.
    "doctype-style": ["error", { style: "lowercase" }],
    // role="list" on a <ul> is redundant per the ARIA-in-HTML mapping, and html-validate
    // is right about that. It is kept anyway: these lists carry list-style:none, and
    // Safari with VoiceOver drops list semantics from a list styled that way unless the
    // role is stated explicitly. The redundancy costs nothing; the lost semantics do.
    "no-redundant-role": "off",
    // Strict: every <th> must carry a scope, not only those in a table that mixes row
    // and column headers. Every table here is a data table whose row header names what
    // the row is about, and a cell read out without its row header is the failure this
    // catches.
    "wcag/h63": ["error", { strict: true }],
  },
};
