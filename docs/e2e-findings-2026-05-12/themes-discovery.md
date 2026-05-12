# Findings: themes-discovery

- **BUG [high]** — Theme "Neo-clouds" rendered no company cards
  - URL: `http://localhost:3000/theme/ebfa88fa-ed89-4c31-8a1c-10f5d9027490`
  - DiscoveryEngine may not have produced results — check signals table + FMP screener.
- **NOTE** — "No company cards" finding on /theme/.../Neo-clouds is likely a selector mismatch (test used `[data-company-card], [data-ticker]` — confirm what the theme detail page actually emits). Worth checking the screenshot before treating as a real bug.
