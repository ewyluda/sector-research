# Findings: reverse-dcf

- **BUG [med]** — ReverseDcfPanel not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-reversedcfpanel.png`
- **BUG [med]** — SensitivityHeatmap not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-sensitivityheatmap.png`
- **BUG [med]** — ThesisVsPricedTable not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-thesisvspricedtable.png`
- **IMPROVEMENT [low]** — No price-override input visible on reverse-DCF tab
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Backend supports ?price=. Consider exposing in WhatIfScratchPanel.
