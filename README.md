# CreditPulse Global — Core Banking Engine

An enterprise-grade core banking engine and financial management platform built with Python and Streamlit. Designed for modern financial institutions, MFIs, and fintech developers to handle full lifecycle banking operations.

---

## 🚀 Key Modules & Features

* **Client Management:** Comprehensive client onboarding, KYC tracking, and directory management.
* **Loan Origination & Credit Scoring:** Automated underwriting parameters, scoring matrices, and loan processing workflows.
* **Repayment Ledgers & Gateways:** Granular tracking of amortization schedules, installments, and payment gateways.
* **Collateral & Guarantor Vault:** Secure asset tracking linked directly to active borrower liabilities.
* **Financial Statements & P&L:** Real-time generation of balance sheets, income statements, and cash flow reports.
* **General Ledger Accounting:** Double-entry ledger management tracking all institutional capital flows.
* **Risk & Collections Engine:** Automated delinquency tracking, IFRS 9 staging, and penalty calculations.

---

## 🛠️ Tech Stack

* **Frontend & UI:** Streamlit
* **Backend:** Python
* **Database:** SQLite / Relational storage (`creditpulse.db`)

---

## ⚙️ Local Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/muendomuthenyam/creditpulse-global-engine.git](https://github.com/muendomuthenyam/creditpulse-global-engine.git)
   cd creditpulse-global-engine
   pip install -r requirements.txt
   streamlit run engine.py
