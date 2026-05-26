export interface StatementRow {
  label: string;
  key: string;
  kind: "money" | "num"; // money → unit-scaled + common-size eligible; num → raw (EPS, shares)
  bold?: boolean;
}

export interface StatementSpec {
  rows: StatementRow[];
  baseKey: string | null;
}

export const INCOME_SPEC: StatementSpec = {
  baseKey: "revenue",
  rows: [
    { label: "Revenue", key: "revenue", kind: "money", bold: true },
    { label: "Cost of Revenue", key: "costOfRevenue", kind: "money" },
    { label: "Gross Profit", key: "grossProfit", kind: "money", bold: true },
    { label: "R&D", key: "researchAndDevelopmentExpenses", kind: "money" },
    { label: "SG&A", key: "sellingGeneralAndAdministrativeExpenses", kind: "money" },
    { label: "Operating Expenses", key: "operatingExpenses", kind: "money" },
    { label: "Operating Income", key: "operatingIncome", kind: "money", bold: true },
    { label: "Interest Expense", key: "interestExpense", kind: "money" },
    { label: "Income Before Tax", key: "incomeBeforeTax", kind: "money" },
    { label: "Income Tax", key: "incomeTaxExpense", kind: "money" },
    { label: "Net Income", key: "netIncome", kind: "money", bold: true },
    { label: "EBITDA", key: "ebitda", kind: "money" },
    { label: "EPS", key: "eps", kind: "num" },
    { label: "EPS (Diluted)", key: "epsDiluted", kind: "num" },
    { label: "Shares (Diluted)", key: "weightedAverageShsOutDil", kind: "money" },
  ],
};

export const BALANCE_SPEC: StatementSpec = {
  baseKey: "totalAssets",
  rows: [
    { label: "Cash & Equivalents", key: "cashAndCashEquivalents", kind: "money" },
    { label: "Short-Term Investments", key: "shortTermInvestments", kind: "money" },
    { label: "Receivables", key: "netReceivables", kind: "money" },
    { label: "Inventory", key: "inventory", kind: "money" },
    { label: "Total Current Assets", key: "totalCurrentAssets", kind: "money", bold: true },
    { label: "PP&E (net)", key: "propertyPlantEquipmentNet", kind: "money" },
    { label: "Goodwill & Intangibles", key: "goodwillAndIntangibleAssets", kind: "money" },
    { label: "Total Assets", key: "totalAssets", kind: "money", bold: true },
    { label: "Accounts Payable", key: "accountPayables", kind: "money" },
    { label: "Short-Term Debt", key: "shortTermDebt", kind: "money" },
    { label: "Total Current Liabilities", key: "totalCurrentLiabilities", kind: "money", bold: true },
    { label: "Long-Term Debt", key: "longTermDebt", kind: "money" },
    { label: "Total Liabilities", key: "totalLiabilities", kind: "money", bold: true },
    { label: "Retained Earnings", key: "retainedEarnings", kind: "money" },
    { label: "Total Equity", key: "totalStockholdersEquity", kind: "money", bold: true },
    { label: "Total Debt", key: "totalDebt", kind: "money" },
    { label: "Net Debt", key: "netDebt", kind: "money" },
  ],
};

export const CASHFLOW_SPEC: StatementSpec = {
  baseKey: null,
  rows: [
    { label: "Net Income", key: "netIncome", kind: "money" },
    { label: "D&A", key: "depreciationAndAmortization", kind: "money" },
    { label: "Stock-Based Comp", key: "stockBasedCompensation", kind: "money" },
    { label: "Change in Working Capital", key: "changeInWorkingCapital", kind: "money" },
    { label: "Operating Cash Flow", key: "netCashProvidedByOperatingActivities", kind: "money", bold: true },
    { label: "CapEx", key: "capitalExpenditure", kind: "money" },
    { label: "Free Cash Flow", key: "freeCashFlow", kind: "money", bold: true },
    { label: "Acquisitions", key: "acquisitionsNet", kind: "money" },
    { label: "Investing Cash Flow", key: "netCashProvidedByInvestingActivities", kind: "money", bold: true },
    { label: "Dividends Paid", key: "netDividendsPaid", kind: "money" },
    { label: "Stock Repurchased", key: "commonStockRepurchased", kind: "money" },
    { label: "Debt Issuance (net)", key: "netDebtIssuance", kind: "money" },
    { label: "Financing Cash Flow", key: "netCashProvidedByFinancingActivities", kind: "money", bold: true },
    { label: "Net Change in Cash", key: "netChangeInCash", kind: "money", bold: true },
  ],
};
