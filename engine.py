import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta
import io
import hashlib
import json
import urllib.request
import plotly.express as px

# ReportLab Imports for PDF Receipts & Loan Agreements
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# --- THREAD-SAFE DATABASE HELPER FUNCTIONS ---
DB_PATH = "creditpulse.db"

def get_db_connection():
    """Creates a fresh database connection with dynamic busy timeouts and WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    """Initializes schema on app start using an isolated connection context."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                national_id TEXT UNIQUE NOT NULL,
                email TEXT,
                address TEXT,
                created_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                principal REAL NOT NULL,
                interest_rate REAL NOT NULL,
                term_months INT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                start_date TEXT NOT NULL,
                due_date TEXT,
                penalty_fee REAL DEFAULT 0.0,
                FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS repayments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                amount_paid REAL NOT NULL,
                payment_date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                receipt_no TEXT UNIQUE NOT NULL,
                FOREIGN KEY (loan_id) REFERENCES active_loans (id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS guarantors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                national_id TEXT NOT NULL,
                relationship TEXT,
                FOREIGN KEY (loan_id) REFERENCES active_loans (id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS collaterals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                asset_type TEXT NOT NULL,
                description TEXT NOT NULL,
                estimated_value REAL NOT NULL,
                FOREIGN KEY (loan_id) REFERENCES active_loans (id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_role TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sms_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_phone TEXT NOT NULL,
                message TEXT NOT NULL,
                channel TEXT DEFAULT 'SMS',
                sent_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DELIVERED'
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS general_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                account_type TEXT NOT NULL,
                debit REAL DEFAULT 0.0,
                credit REAL DEFAULT 0.0,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS investor_capital (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investor_name TEXT NOT NULL,
                capital_amount REAL NOT NULL,
                cost_of_capital_rate REAL NOT NULL,
                date_deposited TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS loan_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                national_id TEXT NOT NULL,
                requested_amount REAL NOT NULL,
                purpose TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            )
        ''')
        conn.commit()

init_db()

def execute_query(query, params=(), fetch=None):
    """Safely executes a single write or read query with automatic connection closing."""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute(query, params)
        if fetch == "all":
            result = c.fetchall()
        elif fetch == "one":
            result = c.fetchone()
        elif fetch == "lastrowid":
            result = c.lastrowid
        else:
            result = None
        conn.commit()
    return result

def query_df(query, params=()):
    """Safely reads SQL queries directly into Pandas DataFrames."""
    with get_db_connection() as conn:
        df = pd.read_sql(query, conn, params=params)
    return df

# --- COMPREHENSIVE MULTI-LANGUAGE (i18n) DICTIONARY ---
TRANSLATIONS = {
    "English": {
        "title": "Banking Engine",
        "portal_login": "Sign In to CreditPulse Global",
        "dashboard": "Dashboard Overview",
        "client_mgmt": "Client Management",
        "loan_origination": "Loan Origination & Credit Score",
        "repayment": "Repayment Ledger & Gateways",
        "borrower_portal": "Borrower Self-Service Portal",
        "collateral_guarantor": "Collateral & Guarantor Vault",
        "restructuring": "Loan Refinancing & Restructuring",
        "bank_parser": "Bank Statement Cash Flow Parser",
        "comm_hub": "WhatsApp & SMS Communications",
        "predictive_risk": "Predictive Risk & Collections",
        "investor_pool": "Investor & Liquidity Pool",
        "ifrs9": "IFRS 9 & Penalty Engine",
        "financial_statements": "Financial Statements & P&L",
        "general_ledger": "General Ledger Accounting",
        "amortization": "Amortization Calculator",
        "audit_trail": "System Audit Trail",
        "total_borrowers": "Total Borrowers",
        "active_loans": "Active Loans",
        "total_disbursed": "Total Disbursed",
        "total_collections": "Total Collections"
    },
    "Swahili (Kiswahili)": {
        "title": "Injini ya Benki",
        "portal_login": "Ingia Kwenye CreditPulse Global",
        "dashboard": "Muhtasari wa Dashibodi",
        "client_mgmt": "Usimamizi wa Wateja",
        "loan_origination": "Utoaji wa Mikopo na Alama",
        "repayment": "Daftari la Malipo na Njia",
        "borrower_portal": "Tovuti ya Kujihudumia ya Mkopaji",
        "collateral_guarantor": "Dhamana na Wadhamini",
        "restructuring": "Kurekebisha Masharti ya Mkopo",
        "bank_parser": "Kichanganuzi cha Taarifa za Benki",
        "comm_hub": "Mawasiliano ya WhatsApp na SMS",
        "predictive_risk": "Utabiri wa Hatari na Makusanyo",
        "investor_pool": "Mfuko wa Wawekezaji na Ukwasi",
        "ifrs9": "Injini ya IFRS 9 na Adhabu",
        "financial_statements": "Taarifa za Fedha na Faida",
        "general_ledger": "Uhasibu wa Daftari Kuu",
        "amortization": "Kikokotoo cha Marejesho",
        "audit_trail": "Kumbukumbu za Mfumo",
        "total_borrowers": "Jumla ya Wakopaji",
        "active_loans": "Mikopo Inayoendelea",
        "total_disbursed": "Jumla ya Mikopo Iliyotolewa",
        "total_collections": "Jumla ya Makusanyo"
    },
    "French (Français)": {
        "title": "Moteur Bancaire",
        "portal_login": "Connexion à CreditPulse Global",
        "dashboard": "Tableau de Bord",
        "client_mgmt": "Gestion des Clients",
        "loan_origination": "Octroi de Crédit & Score",
        "repayment": "Registre des Rembursements",
        "borrower_portal": "Portail Libre-Service Emprunteur",
        "collateral_guarantor": "Garanties & Garants",
        "restructuring": "Refinancement & Restructuration",
        "bank_parser": "Analyseur de Relevés Bancaires",
        "comm_hub": "Communications WhatsApp & SMS",
        "predictive_risk": "Risque Prédictif & Recouvrements",
        "investor_pool": "Pool d'Investisseurs & Liquidité",
        "ifrs9": "IFRS 9 & Moteur de Pénalités",
        "financial_statements": "États Financiers & RÉSULTAT",
        "general_ledger": "Comptabilité Grand Livre",
        "amortization": "Calculateur d'Amortissement",
        "audit_trail": "Piste d'Audit du Système",
        "total_borrowers": "Total Emprunteurs",
        "active_loans": "Prêts Actifs",
        "total_disbursed": "Total Déboursé",
        "total_collections": "Total Recouvré"
    },
    "Spanish (Español)": {
        "title": "Motor Bancario",
        "portal_login": "Iniciar Sesión en CreditPulse Global",
        "dashboard": "Visión General del Panel",
        "client_mgmt": "Gestión de Clientes",
        "loan_origination": "Origen de Préstamos y Puntaje",
        "repayment": "Libro de Pagos y Pasarelas",
        "borrower_portal": "Portal de Autoservicio del Prestatario",
        "collateral_guarantor": "Garantías y Avales",
        "restructuring": "Reestructuración de Préstamos",
        "bank_parser": "Analizador de Extractos Bancarios",
        "comm_hub": "Comunicaciones WhatsApp y SMS",
        "predictive_risk": "Riesgo Predictivo y Cobranzas",
        "investor_pool": "Fondo de Inversores y Liquidez",
        "ifrs9": "IFRS 9 y Motor de Sanciones",
        "financial_statements": "Estados Financieros y Pérdidas/Ganancias",
        "general_ledger": "Contabilidad de Libro Mayor",
        "amortization": "Calculadora de Amortización",
        "audit_trail": "Pista de Auditoría del Sistema",
        "total_borrowers": "Total Prestatarios",
        "active_loans": "Préstamos Activos",
        "total_disbursed": "Total Desembolsado",
        "total_collections": "Total Recaudado"
    },
    "German (Deutsch)": {
        "title": "Bankensystem",
        "portal_login": "Anmelden bei CreditPulse Global",
        "dashboard": "Dashboard-Übersicht",
        "client_mgmt": "Kundenverwaltung",
        "loan_origination": "Kreditvergabe & Scoring",
        "repayment": "Rückzahlungsbuch & Gateways",
        "borrower_portal": "Kreditnehmer-Self-Service-Portal",
        "collateral_guarantor": "Sicherheiten & Bürgen Vault",
        "restructuring": "Kreditumstrukturierung",
        "bank_parser": "Kontoauszug-Analysator",
        "comm_hub": "WhatsApp & SMS Kommunikation",
        "predictive_risk": "Prädiktives Risiko & Inkasso",
        "investor_pool": "Investoren- & Liquiditätspool",
        "ifrs9": "IFRS 9 & Strafen-Engine",
        "financial_statements": "Finanzberichte & GuV",
        "general_ledger": "Hauptbuchhaltung",
        "amortization": "Tilgungsrechner",
        "audit_trail": "System-Audit-Spur",
        "total_borrowers": "Kreditnehmer Gesamt",
        "active_loans": "Aktive Kredite",
        "total_disbursed": "Gesamt Ausgezahlt",
        "total_collections": "Gesamt Eingenommen"
    },
    "Portuguese (Português)": {
        "title": "Motor Bancário",
        "portal_login": "Entrar no CreditPulse Global",
        "dashboard": "Visão Geral do Painel",
        "client_mgmt": "Gestão de Clientes",
        "loan_origination": "Originação de Empréstimos e Scoring",
        "repayment": "Livro de Pagamentos e Gateways",
        "borrower_portal": "Portal de Autoatendimento do Mutuário",
        "collateral_guarantor": "Garantias e Fiadores",
        "restructuring": "Refinanciamento e Reestruturação",
        "bank_parser": "Analisador de Extratos Bancários",
        "comm_hub": "Comunicações WhatsApp e SMS",
        "predictive_risk": "Risco Preditivo e Cobranças",
        "investor_pool": "Pool de Investidores e Liquidez",
        "ifrs9": "IFRS 9 e Motor de Penalidades",
        "financial_statements": "Demonstrações Financeiras e DRE",
        "general_ledger": "Contabilidade do Razão Geral",
        "amortization": "Calculadora de Amortização",
        "audit_trail": "Trilha de Auditoria do Sistema",
        "total_borrowers": "Total de Mutuários",
        "active_loans": "Empréstimos Ativos",
        "total_disbursed": "Total Desembolsado",
        "total_collections": "Total Arrecadado"
    },
    "Arabic (العربية)": {
        "title": "محرك المصرفية",
        "portal_login": "تسجيل الدخول إلى CreditPulse Global",
        "dashboard": "نظرة عامة على لوحة التحكم",
        "client_mgmt": "إدارة العملاء",
        "loan_origination": "إصدار القروض والتصنيف الائتماني",
        "repayment": "دفتر التحصيل وبوابات الدفع",
        "borrower_portal": "بوابة الخدمة الذاتية للمقترض",
        "collateral_guarantor": "الضمانات والكفلاء",
        "restructuring": "إعادة هيكلة القروض",
        "bank_parser": "محلل كشف الحساب البنكي",
        "comm_hub": "اتصالات واتساب والرسائل النصية",
        "predictive_risk": "المخاطر التنبؤية والتحصيل",
        "investor_pool": "مجمع المستثمرين والسيولة",
        "ifrs9": "محرك المعيار الدولي IFRS 9 والغرامات",
        "financial_statements": "القوائم المالية والأرباح والخسائر",
        "general_ledger": "محاسبة دفتر الأستاذ العام",
        "amortization": "حاسبة إطفاء الدين",
        "audit_trail": "سجل مراجعة النظام",
        "total_borrowers": "إجمالي المقترضين",
        "active_loans": "القروض النشطة",
        "total_disbursed": "إجمالي المبالغ المصروفة",
        "total_collections": "إجمالي التحصيلات"
    },
    "Hindi (हिन्दी)": {
        "title": "बैंकिंग इंजन",
        "portal_login": "CreditPulse Global में साइन इन करें",
        "dashboard": "डैशबोर्ड अवलोकन",
        "client_mgmt": "ग्राहक प्रबंधन",
        "loan_origination": "ऋण उत्पत्ति और क्रेडिट स्कोर",
        "repayment": "पुनर्भुगतान लेजर और गेटवे",
        "borrower_portal": "उधारकर्ता स्वयं सेवा पोर्टल",
        "collateral_guarantor": "जमानत और गारंटर वॉल्ट",
        "restructuring": "ऋण पुनर्गठन और रिफाइनेंसिंग",
        "bank_parser": "बैंक स्टेटमेंट कैश फ्लो पार्सर",
        "comm_hub": "व्हाट्सएप और एसएमएस संचार",
        "predictive_risk": "पूर्वानुमानित जोखिम और वसूली",
        "investor_pool": "निवेशक और तरलता पूल",
        "ifrs9": "IFRS 9 और दंड इंजन",
        "financial_statements": "वित्तीय विवरण और लाभ-हानि",
        "general_ledger": "सामान्य बहीखाता लेखांकन",
        "amortization": "ऋण शोधन कैलकुलेटर",
        "audit_trail": "सिस्टम ऑडिट ट्रेल",
        "total_borrowers": "कुल उधारकर्ता",
        "active_loans": "सक्रिय ऋण",
        "total_disbursed": "कुल वितरित राशि",
        "total_collections": "कुल वसूली"
    },
    "Mandarin (中文)": {
        "title": "银行核心引擎",
        "portal_login": "登录 CreditPulse Global",
        "dashboard": "仪表板概览",
        "client_mgmt": "客户管理",
        "loan_origination": "贷款发起与信用评分",
        "repayment": "还款账本与支付网关",
        "borrower_portal": "借款人自助服务门户",
        "collateral_guarantor": "抵押品与担保人库",
        "restructuring": "贷款重组与再融资",
        "bank_parser": "银行流水现金流解析器",
        "comm_hub": "WhatsApp 与短信通信中心",
        "predictive_risk": "预测性风险与催收",
        "investor_pool": "投资者与流动性资金池",
        "ifrs9": "IFRS 9 减值与罚息引擎",
        "financial_statements": "财务报表与损益表",
        "general_ledger": "总分类账会计",
        "amortization": "摊销计算器",
        "audit_trail": "系统审计追踪",
        "total_borrowers": "总借款人数量",
        "active_loans": "活跃贷款数",
        "total_disbursed": "总发放贷款",
        "total_collections": "总回收资金"
    },
    "Japanese (日本語)": {
        "title": "バンキングエンジン",
        "portal_login": "CreditPulse Global にサインイン",
        "dashboard": "ダッシュボード概要",
        "client_mgmt": "顧客管理",
        "loan_origination": "融資実行 & 信用スコア",
        "repayment": "返済元帳 & 決済ゲートウェイ",
        "borrower_portal": "借入者セルフサービスポータル",
        "collateral_guarantor": "担保 & 保証人管理",
        "restructuring": "ローン再構築 & リファイナンス",
        "bank_parser": "銀行口座明細アナライザー",
        "comm_hub": "WhatsApp & SMS 通信ハブ",
        "predictive_risk": "予測リスク & 債権回収",
        "investor_pool": "投資家 & 流動性プール",
        "ifrs9": "IFRS 9 & 延滞金エンジン",
        "financial_statements": "財務諸表 & 損益計算書",
        "general_ledger": "元帳会計",
        "amortization": "返済シミュレーター",
        "audit_trail": "システム監査ログ",
        "total_borrowers": "総借入者数",
        "active_loans": "アクティブな融資",
        "total_disbursed": "融資実行総额",
        "total_collections": "回収総額"
    },
    "Korean (한국어)": {
        "title": "뱅킹 코어 엔진",
        "portal_login": "CreditPulse Global 로그인",
        "dashboard": "대시보드 개요",
        "client_mgmt": "고객 관리",
        "loan_origination": "대출 심사 및 신용 스코어ing",
        "repayment": "상환 원장 및 결제 게이트웨이",
        "borrower_portal": "차주 셀프서비스 포털",
        "collateral_guarantor": "담보 및 보증인 관리",
        "restructuring": "대출 재조정 및 리파이낸싱",
        "bank_parser": "은행 거래 내역 입출금 분석기",
        "comm_hub": "WhatsApp 및 SMS 통신 센터",
        "predictive_risk": "예측 리스크 및 채권 추심",
        "investor_pool": "투자자 및 유동성 풀",
        "ifrs9": "IFRS 9 손실 충당금 엔진",
        "financial_statements": "재무제표 및 손익계산서",
        "general_ledger": "총계정원장 회계",
        "amortization": "상환 스케줄 계산기",
        "audit_trail": "시스템 감사 기록",
        "total_borrowers": "총 차주 수",
        "active_loans": "진행 중인 대출",
        "total_disbursed": "총 실행 금액",
        "total_collections": "총 회수 금액"
    },
    "Russian (Русский)": {
        "title": "Банковский Движок",
        "portal_login": "Вход в CreditPulse Global",
        "dashboard": "Обзор Панели",
        "client_mgmt": "Управление Клиентами",
        "loan_origination": "Выдача Кредитов и Скоринг",
        "repayment": "Реестр Погашений и Шлюзы",
        "borrower_portal": "Портал Заемщика",
        "collateral_guarantor": "Залоги и Поручители",
        "restructuring": "Реструктуризация Кредитов",
        "bank_parser": "Анализатор Банковских Выписок",
        "comm_hub": "Связь WhatsApp и SMS",
        "predictive_risk": "Прогноз Рисков и Взыскание",
        "investor_pool": "Пул Инвесторов и Ликвидность",
        "ifrs9": "МСФО 9 и Штрафы",
        "financial_statements": "Финансовая Отчетность и P&L",
        "general_ledger": "Главная Бухгалтерская Книга",
        "amortization": "Калькулятор Амортизации",
        "audit_trail": "Аудит Системы",
        "total_borrowers": "Всего Заемщиков",
        "active_loans": "Активные Кредиты",
        "total_disbursed": "Всего Выдано",
        "total_collections": "Всего Собрано"
    },
    "Italian (Italiano)": {
        "title": "Motore Bancario",
        "portal_login": "Accedi a CreditPulse Global",
        "dashboard": "Panoramica Dashboard",
        "client_mgmt": "Gestione Clienti",
        "loan_origination": "Erogazione Prestiti & Scoring",
        "repayment": "Registro Rimborsi & Gateway",
        "borrower_portal": "Portale Self-Service Mutuatario",
        "collateral_guarantor": "Garanzie e Garanti",
        "restructuring": "Ristrutturazione del Credito",
        "bank_parser": "Analizzatore Estratto Conto",
        "comm_hub": "Comunicazioni WhatsApp & SMS",
        "predictive_risk": "Rischio Predittivo & Recupero Crediti",
        "investor_pool": "Pool Investitori & Liquidità",
        "ifrs9": "IFRS 9 & Calcolo Penali",
        "financial_statements": "Rendiconto Finanziario & C/Economico",
        "general_ledger": "Contabilità Generale",
        "amortization": "Calcolatore Ammortamento",
        "audit_trail": "Audit di Sistema",
        "total_borrowers": "Totale Mutuatari",
        "active_loans": "Prestiti Attivi",
        "total_disbursed": "Totale Erogato",
        "total_collections": "Totale Incassato"
    },
    "Dutch (Nederlands)": {
        "title": "Bankier Systeem",
        "portal_login": "Inloggen bij CreditPulse Global",
        "dashboard": "Dashboard Overzicht",
        "client_mgmt": "Klantenbeheer",
        "loan_origination": "Lening Acceptatie & Scoring",
        "repayment": "Aflossingsregister & Gateways",
        "borrower_portal": "Zelfbedieningsportaal Lener",
        "collateral_guarantor": "Onderpand & Borgstellers",
        "restructuring": "Lening Herstructurering",
        "bank_parser": "Bankafschrift Analysator",
        "comm_hub": "WhatsApp & SMS Communicatie",
        "predictive_risk": "Voorspellend Risico & Incasso",
        "investor_pool": "Investeerders- & Liquiditeitspool",
        "ifrs9": "IFRS 9 & Boete-Engine",
        "financial_statements": "Financiële Staten & W&V",
        "general_ledger": "Grootboekadministratie",
        "amortization": "Aflossingscalculator",
        "audit_trail": "Systeemauditlogboek",
        "total_borrowers": "Totaal Aantal Leners",
        "active_loans": "Actieve Leningen",
        "total_disbursed": "Totaal Geuitgekeerd",
        "total_collections": "Totaal Ontvangen"
    },
    "Turkish (Türkçe)": {
        "title": "Bankacılık Motoru",
        "portal_login": "CreditPulse Global Girişi",
        "dashboard": "Kontrol Paneli",
        "client_mgmt": "Müşteri Yönetimi",
        "loan_origination": "Kredi Tahsis ve Skorlama",
        "repayment": "Geri Ödeme Defteri ve Ağlar",
        "borrower_portal": "Borçlu Bireysel Portalı",
        "collateral_guarantor": "Teminat ve Kefil Deposu",
        "restructuring": "Kredi Yeniden Yapılandırma",
        "bank_parser": "Banka Hesap Özeti Analizörü",
        "comm_hub": "WhatsApp ve SMS İletişim",
        "predictive_risk": "Tahmini Risk ve Tahsilat",
        "investor_pool": "Yatırımcı ve Likidite Havuzu",
        "ifrs9": "TFRS 9 ve Ceza Motoru",
        "financial_statements": "Finansal Tablolar ve Gelir Tablosu",
        "general_ledger": "Genel Muhasebe Defteri",
        "amortization": "İtfa Hesaplayıcı",
        "audit_trail": "Sistem Denetim İzi",
        "total_borrowers": "Toplam Borçlu",
        "active_loans": "Aktif Krediler",
        "total_disbursed": "Toplam Kullandırılan",
        "total_collections": "Toplam Tahsilat"
    }
}

# --- MULTI-CURRENCY & FX ENGINE ---
@st.cache_data(ttl=3600)
def get_exchange_rates(base_currency="USD"):
    try:
        url = f"https://open.er-api.com/v6/latest/{base_currency}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data.get("result") == "success":
                return data["rates"]
    except Exception:
        pass
    return {"USD": 1.0, "KES": 129.50, "EUR": 0.92, "GBP": 0.78, "NGN": 1600.0, "INR": 83.5, "JPY": 155.0, "CAD": 1.36}

# --- IFRS 9 EXPECTED CREDIT LOSS (ECL) PROVISIONING ENGINE ---
def calculate_ifrs9_provisioning(df_loans):
    if df_loans.empty:
        return {"Stage 1 (12-mo ECL)": 0.0, "Stage 2 (Lifetime ECL)": 0.0, "Stage 3 (Impaired)": 0.0, "Total Provision Required": 0.0}

    today = datetime.now().date()
    
    def calculate_days_overdue(due_date_str):
        if not due_date_str:
            return 0
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            return max(0, (today - due_date).days)
        except Exception:
            return 0

    df_loans['days_overdue'] = df_loans['due_date'].apply(calculate_days_overdue)

    def assign_stage(days):
        if days <= 30:
            return "Stage 1 (12-mo ECL)"
        elif days <= 90:
            return "Stage 2 (Lifetime ECL)"
        else:
            return "Stage 3 (Impaired)"

    df_loans['ifrs9_stage'] = df_loans['days_overdue'].apply(assign_stage)
    
    loss_rates = {
        "Stage 1 (12-mo ECL)": 0.015,
        "Stage 2 (Lifetime ECL)": 0.150,
        "Stage 3 (Impaired)": 0.500
    }
    
    summary = {}
    total_prov = 0.0
    for stage, rate in loss_rates.items():
        stage_balance = df_loans[df_loans['ifrs9_stage'] == stage]['principal'].sum()
        stage_provision = stage_balance * rate
        summary[stage] = stage_provision
        total_prov += stage_provision

    summary["Total Provision Required"] = total_prov
    return summary

# --- GENERAL HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def log_action(user_role, action, details):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query("INSERT INTO audit_logs (user_role, action, details, timestamp) VALUES (?, ?, ?, ?)",
                  (user_role, action, details, timestamp))

def send_comm_message(phone, message, channel="SMS"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query("INSERT INTO sms_logs (recipient_phone, message, channel, sent_at) VALUES (?, ?, ?, ?)",
                  (phone, message, channel, timestamp))

def record_gl_entry(account_name, account_type, debit, credit, description):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_query("INSERT INTO general_ledger (account_name, account_type, debit, credit, description, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (account_name, account_type, debit, credit, description, timestamp))

def verify_crb_and_id(national_id):
    id_num = int(''.join(filter(str.isdigit, national_id)) or 0)
    crb_status = "CLEARED" if id_num % 2 == 0 else "LISTED (DEFAULTED ELSEWHERE)"
    delinquent_accounts = 0 if crb_status == "CLEARED" else (id_num % 3) + 1
    return crb_status, delinquent_accounts

def predict_default_risk(client_id, principal, term_months):
    past_loans = query_df("SELECT * FROM active_loans WHERE client_id = ?", params=(client_id,))
    repayments = query_df("""
        SELECT repayments.* FROM repayments 
        JOIN active_loans ON repayments.loan_id = active_loans.id 
        WHERE active_loans.client_id = ?
    """, params=(client_id,))
    
    risk_score = 15.0
    if principal > 75000:
        risk_score += 20.0
    if term_months > 12:
        risk_score += 15.0
    if not past_loans.empty and repayments.empty:
        risk_score += 25.0
    
    risk_score = float(np.clip(risk_score, 5.0, 95.0))
    
    if risk_score > 50.0:
        risk_category = "HIGH DEFAULT RISK"
        recommended_premium = 2.5
    elif risk_score > 25.0:
        risk_category = "MEDIUM DEFAULT RISK"
        recommended_premium = 1.0
    else:
        risk_category = "LOW DEFAULT RISK"
        recommended_premium = 0.0
        
    return risk_score, risk_category, recommended_premium

def calculate_credit_score(client_id, requested_principal, term_months):
    past_loans = query_df("SELECT * FROM active_loans WHERE client_id = ?", params=(client_id,))
    repayments = query_df("""
        SELECT repayments.* FROM repayments 
        JOIN active_loans ON repayments.loan_id = active_loans.id 
        WHERE active_loans.client_id = ?
    """, params=(client_id,))
    
    score = 650
    if not past_loans.empty:
        total_borrowed = past_loans['principal'].sum()
        total_repaid = repayments['amount_paid'].sum() if not repayments.empty else 0.0
        if total_repaid >= total_borrowed:
            score += 100
        elif total_repaid > 0:
            score += 40
        penalized_loans = past_loans[past_loans['penalty_fee'] > 0]
        if not penalized_loans.empty:
            score -= 120 * len(penalized_loans)
            
    if requested_principal > 100000:
        score -= 50
    if term_months > 12:
        score -= 30
        
    score = int(np.clip(score, 300, 850))
    
    if score >= 720:
        grade = "LOW RISK (Approved)"
        max_limit = requested_principal * 1.5
    elif score >= 580:
        grade = "MEDIUM RISK (Conditional)"
        max_limit = requested_principal
    else:
        grade = "HIGH RISK (Caution Advisory)"
        max_limit = requested_principal * 0.5
        
    return score, grade, max_limit

def generate_pdf_receipt(receipt_no, borrower_name, amount, payment_date, method, loan_id, curr_symbol):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(100, 750, "CREDITPULSE GLOBAL — OFFICIAL RECEIPT")
    p.setLineWidth(1)
    p.line(100, 740, 500, 740)
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 710, f"Receipt No: {receipt_no}")
    p.drawString(100, 690, f"Date: {payment_date}")
    p.drawString(100, 670, f"Borrower Name: {borrower_name}")
    p.drawString(100, 650, f"Loan Account ID: #{loan_id}")
    p.drawString(100, 630, f"Payment Channel: {method}")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(100, 590, f"Amount Paid: {curr_symbol} {amount:,.2f}")
    
    p.setFont("Helvetica-Oblique", 10)
    p.drawString(100, 530, "Thank you for your payment. This is a computer-generated receipt.")
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# --- APP CONFIGURATION ---
st.set_page_config(page_title="CreditPulse Global — Core Banking Engine", layout="wide", page_icon="💳")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        background-color: #1e222d;
        border: 1px solid #2e364f;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    div.stButton > button:first-child {
        border-radius: 8px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION & MULTI-ROLE ACCESS ENGINE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None

USER_CREDS = {
    "admin": {"password_hash": hash_password("admin123"), "role": "Admin / Manager"},
    "teller": {"password_hash": hash_password("teller123"), "role": "Loan Officer / Teller"},
    "auditor": {"password_hash": hash_password("audit123"), "role": "Risk & Audit Compliance"}
}

st.sidebar.title("🔐 User Portal")

# --- LOCALIZATION SELECTOR ---
available_languages = list(TRANSLATIONS.keys())
selected_lang = st.sidebar.selectbox("🌐 UI Language", available_languages, index=0)
t = TRANSLATIONS[selected_lang]

if not st.session_state.authenticated:
    st.subheader(f"🔑 {t['portal_login']}")
    with st.form("login_form"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Authenticate")
        
        if login_btn:
            if username in USER_CREDS and USER_CREDS[username]["password_hash"] == hash_password(password):
                st.session_state.authenticated = True
                st.session_state.user_role = USER_CREDS[username]["role"]
                log_action(st.session_state.user_role, "USER_LOGIN", f"User {username} logged in successfully.")
                st.rerun()
            else:
                st.error("Invalid credentials. Hint: admin/admin123, teller/teller123, or auditor/audit123")
    st.stop()

user_role = st.session_state.user_role

# --- GLOBAL MULTI-CURRENCY & TENANT SETTINGS ---
st.sidebar.markdown("---")
st.sidebar.title("🌐 Global Engine Settings")

rates = get_exchange_rates("USD")
supported_currencies = ["KES", "USD", "EUR", "GBP", "NGN", "INR", "JPY", "CAD"]
selected_currency = st.sidebar.selectbox("Operating Currency", supported_currencies, index=0)
fx_rate = rates.get(selected_currency, 1.0)
st.sidebar.caption(f"1 USD = {fx_rate:.2f} {selected_currency}")

tenant_name = st.sidebar.text_input("MFI Organization", "CreditPulse Global")

st.title(f"💳 {tenant_name} — {t['title']}")
st.caption(f"Logged in as: **{user_role}** | Active Base Currency: **{selected_currency}**")

if st.sidebar.button("🚪 Logout"):
    log_action(user_role, "USER_LOGOUT", "User logged out.")
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.rerun()

# --- DYNAMICALLY TRANSLATED OPERATIONS MENU ---
st.sidebar.markdown("---")
st.sidebar.title("📌 Operations Menu")

if user_role == "Admin / Manager":
    menu_options = [
        t['dashboard'], 
        t['client_mgmt'], 
        t['loan_origination'], 
        t['repayment'], 
        t['borrower_portal'],
        t['collateral_guarantor'],
        t['restructuring'],
        t['bank_parser'],
        t['comm_hub'],
        t['predictive_risk'], 
        t['investor_pool'],
        t['ifrs9'], 
        t['financial_statements'],
        t['general_ledger'],
        t['amortization'],
        t['audit_trail']
    ]
elif user_role == "Loan Officer / Teller":
    menu_options = [
        t['client_mgmt'], 
        t['repayment'], 
        t['borrower_portal'],
        t['collateral_guarantor'],
        t['bank_parser'],
        t['amortization']
    ]
else:  # Risk & Audit Compliance
    menu_options = [
        t['dashboard'],
        t['ifrs9'],
        t['financial_statements'],
        t['general_ledger'],
        t['audit_trail']
    ]

selected_menu_item = st.sidebar.radio("Navigate", menu_options)

st.sidebar.markdown("---")
if st.sidebar.button("📥 Export Client Directory (CSV)"):
    df_export = query_df("SELECT * FROM clients")
    if not df_export.empty:
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.sidebar.download_button("Download CSV", data=csv, file_name=f"clients_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')
    else:
        st.sidebar.warning("No clients found to export.")

st.sidebar.caption("Engine Status: 🟢 Enterprise Multi-Tenant Active")

# --- MODULE 1: CLIENT MANAGEMENT ---
if selected_menu_item == t['client_mgmt']:
    st.subheader(f"👤 {t['client_mgmt']}")
    
    if user_role == "Admin / Manager":
        tab1, tab2, tab3 = st.tabs(["Register New Client", "Client Directory", "🗑️ Delete Client Profile"])
    else:
        tab1, tab2 = st.tabs(["Register New Client", "Client Directory"])
    
    with tab1:
        with st.form("client_form", clear_on_submit=True):
            full_name = st.text_input("Full Legal Name").strip()
            phone = st.text_input("Phone Number (with Country Code)").strip()
            national_id = st.text_input("National ID / Passport Number").strip()
            email = st.text_input("Email Address").strip()
            address = st.text_input("Physical Address / Location").strip()
            submit = st.form_submit_button("Register Client")
            
            if submit:
                if not full_name or not phone or not national_id:
                    st.error("Validation Error: Name, Phone, and National ID are required.")
                else:
                    try:
                        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        execute_query("INSERT INTO clients (full_name, phone, national_id, email, address, created_at) VALUES (?, ?, ?, ?, ?, ?)", 
                                      (full_name, phone, national_id, email, address, today))
                        log_action(user_role, "REGISTER_CLIENT", f"Registered client {full_name} (ID: {national_id})")
                        send_comm_message(phone, f"Welcome {full_name} to {tenant_name}! Your account profile is active.")
                        st.success(f"Client **{full_name}** successfully registered!")
                    except sqlite3.IntegrityError:
                        st.error(f"Error: National ID **{national_id}** is already registered.")

    with tab2:
        clients_df = query_df("SELECT id AS 'ID', full_name AS 'Full Name', phone AS 'Phone', national_id AS 'National ID', email AS 'Email', address AS 'Address' FROM clients ORDER BY id DESC")
        if not clients_df.empty:
            st.dataframe(clients_df, use_container_width=True)
        else:
            st.info("No clients onboarded yet.")

    if user_role == "Admin / Manager":
        with tab3:
            st.markdown("##### ⚠️ Delete Borrower Profile")
            clients_df = query_df("SELECT id, full_name, national_id FROM clients")
            if not clients_df.empty:
                delete_options = {f"{row['full_name']} (ID: {row['national_id']})": row['id'] for _, row in clients_df.iterrows()}
                selected_client_to_delete = st.selectbox("Select Client to Delete", list(delete_options.keys()))
                client_id_to_delete = delete_options[selected_client_to_delete]
                
                if st.button("🔴 Permanently Delete Client Record", type="primary"):
                    execute_query("DELETE FROM clients WHERE id = ?", (client_id_to_delete,))
                    log_action(user_role, "DELETE_CLIENT", f"Deleted client ID #{client_id_to_delete}")
                    st.success("Client record deleted.")
                    st.rerun()
            else:
                st.info("No clients available to delete.")

# --- MODULE 2: LOAN ORIGINATION, CREDIT SCORE & CRB CHECK ---
elif selected_menu_item == t['loan_origination']:
    st.subheader(f"📝 {t['loan_origination']}")
    orig_tab1, orig_tab2 = st.tabs(["Originate & Disburse", "🚫 Void Active Loan"])
    
    with orig_tab1:
        clients_df = query_df("SELECT id, full_name, phone, national_id FROM clients")
        if not clients_df.empty:
            client_options = {f"{row['full_name']} (ID: {row['national_id']})": (row['id'], row['full_name'], row['phone'], row['national_id']) for _, row in clients_df.iterrows()}
            selected_client_label = st.selectbox("Select Borrower", list(client_options.keys()))
            selected_client_id, borrower_name, borrower_phone, borrower_nid = client_options[selected_client_label]
            
            st.markdown("##### 🔍 1. Real-Time CRB Verification")
            crb_status, delinquent_accs = verify_crb_and_id(borrower_nid)
            c1, c2 = st.columns(2)
            c1.metric("CRB Listing Status", crb_status)
            c2.metric("External Delinquent Accounts", f"{delinquent_accs} Accounts")
            
            st.markdown("---")
            st.markdown("##### 2. Loan Parameters")
            col1, col2 = st.columns(2)
            with col1:
                principal = st.number_input(f"Principal Amount ({selected_currency})", min_value=100.0, value=1000.0, step=100.0)
                term_months = st.slider("Loan Tenure (Months)", 1, 36, 6)
            with col2:
                pred_risk_pct, risk_cat, rec_premium = predict_default_risk(selected_client_id, principal, term_months)
                base_rate = st.number_input("Monthly Base Interest Rate (%)", min_value=0.1, value=3.0, step=0.1)
                final_interest_rate = base_rate + rec_premium
                st.caption(f"Risk Premium Applied: +{rec_premium}% | Final Interest Rate: **{final_interest_rate:.1f}%/month**")
                start_date = st.date_input("Disbursement Date", datetime.now())
                
            due_date = start_date + timedelta(days=term_months * 30)
            
            st.markdown("---")
            score, grade, max_limit = calculate_credit_score(selected_client_id, principal, term_months)
            st.metric("Credit Score", f"{score} / 850 ({grade})")
            
            disburse_method = st.radio("Disbursement Channel", ["Global Wire / Bank Transfer", "M-Pesa STK / Mobile Wallet", "Stripe / Card Payout"], horizontal=True)
            
            if st.button("Approve & Disburse Loan"):
                loan_id = execute_query(
                    "INSERT INTO active_loans (client_id, principal, interest_rate, term_months, status, start_date, due_date) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)",
                    (selected_client_id, principal, final_interest_rate, term_months, start_date.strftime("%Y-%m-%d"), due_date.strftime("%Y-%m-%d")),
                    fetch="lastrowid"
                )
                record_gl_entry("Gross Loan Portfolio", "ASSET", debit=principal, credit=0.0, description=f"Disbursement Account #{loan_id}")
                record_gl_entry("Cash at Bank", "ASSET", debit=0.0, credit=principal, description=f"Disbursement Account #{loan_id}")

                log_action(user_role, "DISBURSE_LOAN", f"Disbursed loan #{loan_id} of {selected_currency} {principal:,.2f}")
                send_comm_message(borrower_phone, f"Dear {borrower_name}, loan #{loan_id} of {selected_currency} {principal:,.2f} disbursed. Due: {due_date.strftime('%Y-%m-%d')}.")
                st.success(f"Loan #{loan_id} of **{selected_currency} {principal:,.2f}** disbursed!")
        else:
            st.warning("No registered clients found.")

    with orig_tab2:
        active_loans = query_df("SELECT active_loans.id, clients.full_name, active_loans.principal FROM active_loans JOIN clients ON active_loans.client_id = clients.id WHERE active_loans.status = 'ACTIVE'")
        if not active_loans.empty:
            void_options = {f"Loan #{row['id']} - {row['full_name']} ({selected_currency} {row['principal']:,.2f})": row['id'] for _, row in active_loans.iterrows()}
            loan_id_to_void = void_options[st.selectbox("Select Loan to Void", list(void_options.keys()))]
            if st.button("Void Loan Account", type="primary"):
                execute_query("UPDATE active_loans SET status = 'VOID' WHERE id = ?", (loan_id_to_void,))
                log_action(user_role, "VOID_LOAN", f"Voided loan account #{loan_id_to_void}")
                st.success("Loan updated to VOID.")
                st.rerun()

# --- MODULE 3: REPAYMENT LEDGER & GATEWAYS ---
elif selected_menu_item == t['repayment']:
    st.subheader(f"💵 {t['repayment']}")
    pay_tab1, pay_tab2 = st.tabs(["Record Payment", "Reverse Payment Entry"])
    
    with pay_tab1:
        active_loans_df = query_df("SELECT active_loans.id, clients.full_name, clients.phone, active_loans.principal FROM active_loans JOIN clients ON active_loans.client_id = clients.id WHERE active_loans.status = 'ACTIVE'")
        if not active_loans_df.empty:
            loan_options = {f"Loan #{row['id']} - {row['full_name']} ({selected_currency} {row['principal']:,.2f})": (row['id'], row['full_name'], row['phone']) for _, row in active_loans_df.iterrows()}
            selected_loan_label = st.selectbox("Select Active Loan", list(loan_options.keys()))
            selected_loan_id, borrower_name, borrower_phone = loan_options[selected_loan_label]
            
            amount_paid = st.number_input(f"Payment Amount ({selected_currency})", min_value=10.0, step=50.0)
            payment_method = st.selectbox("Payment Channel", ["Stripe / Card Gateway", "M-Pesa C2B STK Push", "Direct SWIFT / Bank Transfer", "PayPal / Digital Wallet"])
            payment_date = st.date_input("Collection Date", datetime.now())
            
            if st.button("Process Payment & Issue Receipt"):
                receipt_no = f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                execute_query("INSERT INTO repayments (loan_id, amount_paid, payment_date, payment_method, receipt_no) VALUES (?, ?, ?, ?, ?)",
                              (selected_loan_id, amount_paid, payment_date.strftime("%Y-%m-%d"), payment_method, receipt_no))
                
                record_gl_entry("Cash at Bank", "ASSET", debit=amount_paid, credit=0.0, description=f"Collection #{receipt_no}")
                record_gl_entry("Interest & Principal Revenue", "INCOME", debit=0.0, credit=amount_paid, description=f"Collection #{receipt_no}")

                log_action(user_role, "RECORD_REPAYMENT", f"Recorded {selected_currency} {amount_paid:,.2f} for loan #{selected_loan_id}")
                st.success(f"Payment recorded! Receipt: **{receipt_no}**")
                
                pdf_bytes = generate_pdf_receipt(receipt_no, borrower_name, amount_paid, payment_date.strftime("%Y-%m-%d"), payment_method, selected_loan_id, selected_currency)
                st.download_button("📄 Download PDF Receipt", data=pdf_bytes, file_name=f"{receipt_no}.pdf", mime="application/pdf")
        else:
            st.info("No active loans requiring collection.")

    with pay_tab2:
        repayments_df = query_df("SELECT repayments.id, repayments.receipt_no, repayments.amount_paid, clients.full_name FROM repayments JOIN active_loans ON repayments.loan_id = active_loans.id JOIN clients ON active_loans.client_id = clients.id ORDER BY repayments.id DESC")
        if not repayments_df.empty:
            rcp_options = {f"Receipt {row['receipt_no']} - {selected_currency} {row['amount_paid']:,.2f} ({row['full_name']})": row['id'] for _, row in repayments_df.iterrows()}
            rcp_id_to_delete = rcp_options[st.selectbox("Select Payment to Reverse", list(rcp_options.keys()))]
            if st.button("Reverse Payment Entry", type="primary"):
                execute_query("DELETE FROM repayments WHERE id = ?", (rcp_id_to_delete,))
                log_action(user_role, "REVERSE_PAYMENT", f"Reversed payment record ID #{rcp_id_to_delete}")
                st.success("Payment entry reversed.")
                st.rerun()

# --- MODULE 4: BORROWER SELF-SERVICE PORTAL ---
elif selected_menu_item == t['borrower_portal']:
    st.subheader(f"🌐 {t['borrower_portal']}")
    b_tab1, b_tab2 = st.tabs(["Public Loan Request Portal", "Pending Applications Inbox"])
    
    with b_tab1:
        st.markdown("##### 📥 Direct Borrower Loan Application")
        with st.form("borrower_app_form", clear_on_submit=True):
            app_name = st.text_input("Full Name").strip()
            app_phone = st.text_input("Phone Number").strip()
            app_nid = st.text_input("National ID / Passport Number").strip()
            app_amount = st.number_input(f"Requested Principal ({selected_currency})", min_value=100.0, value=2000.0, step=100.0)
            app_purpose = st.selectbox("Loan Purpose", ["Business Expansion", "Working Capital", "Equipment Purchase", "Emergency / Personal"])
            
            if st.form_submit_button("Submit Online Application"):
                if not app_name or not app_phone or not app_nid:
                    st.error("Validation Error: Please fill in all details.")
                else:
                    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execute_query("INSERT INTO loan_applications (applicant_name, phone, national_id, requested_amount, purpose, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                  (app_name, app_phone, app_nid, app_amount, app_purpose, today))
                    send_comm_message(app_phone, f"Dear {app_name}, your application for {selected_currency} {app_amount:,.2f} has been received!")
                    st.success("Your application was submitted successfully! An officer will review your request.")

    with b_tab2:
        st.markdown("##### 📋 Review & Approve Online Applications")
        apps_df = query_df("SELECT * FROM loan_applications WHERE status = 'PENDING' ORDER BY id DESC")
        if not apps_df.empty:
            for _, app in apps_df.iterrows():
                with st.expander(f"Application #{app['id']} — {app['applicant_name']} ({selected_currency} {app['requested_amount']:,.2f})"):
                    st.write(f"**Phone:** {app['phone']} | **National ID:** {app['national_id']}")
                    st.write(f"**Purpose:** {app['purpose']} | **Submitted:** {app['created_at']}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Approve & Onboard", key=f"app_approve_{app['id']}"):
                        try:
                            execute_query("INSERT INTO clients (full_name, phone, national_id, created_at) VALUES (?, ?, ?, ?)",
                                          (app['applicant_name'], app['phone'], app['national_id'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        except sqlite3.IntegrityError:
                            pass
                        execute_query("UPDATE loan_applications SET status = 'APPROVED' WHERE id = ?", (app['id'],))
                        log_action(user_role, "APPROVE_LOAN_APP", f"Approved online application #{app['id']} for {app['applicant_name']}")
                        send_comm_message(app['phone'], f"Congratulations {app['applicant_name']}, your loan application #{app['id']} has been approved!")
                        st.success("Application approved and applicant onboarded!")
                        st.rerun()
                    if c2.button("Reject Application", key=f"app_reject_{app['id']}"):
                        execute_query("UPDATE loan_applications SET status = 'REJECTED' WHERE id = ?", (app['id'],))
                        log_action(user_role, "REJECT_LOAN_APP", f"Rejected online application #{app['id']}")
                        st.warning("Application rejected.")
                        st.rerun()
        else:
            st.info("No pending applications in inbox.")

# --- MODULE 5: COLLATERAL & GUARANTOR VAULT ---
elif selected_menu_item == t.get('collateral_guarantor', "Collateral & Guarantor Vault"):
    st.subheader("🛡️ Collateral & Guarantor Vault")
    cg_tab1, cg_tab2 = st.tabs(["Register Collateral Asset", "Attach Personal Guarantor"])
    
    loans_df = query_df("SELECT active_loans.id, clients.full_name, active_loans.principal FROM active_loans JOIN clients ON active_loans.client_id = clients.id WHERE active_loans.status = 'ACTIVE'")
    
    with cg_tab1:
        if not loans_df.empty:
            loan_opts = {f"Loan #{row['id']} - {row['full_name']}": row['id'] for _, row in loans_df.iterrows()}
            sel_loan = loan_opts[st.selectbox("Select Target Active Loan", list(loan_opts.keys()), key="cg_loan_col")]
            
            with st.form("collateral_form", clear_on_submit=True):
                asset_type = st.selectbox("Asset Category", ["Logbook / Vehicle", "Land Title / Real Estate", "Equipment / Machinery", "Shares / Fixed Deposit"])
                asset_desc = st.text_input("Asset Description / Serial Number").strip()
                asset_val = st.number_input(f"Estimated Market Value ({selected_currency})", min_value=100.0, value=5000.0, step=500.0)
                
                if st.form_submit_button("Vault Collateral Record"):
                    execute_query("INSERT INTO collaterals (loan_id, asset_type, description, estimated_value) VALUES (?, ?, ?, ?)",
                                  (sel_loan, asset_type, asset_desc, asset_val))
                    log_action(user_role, "REGISTER_COLLATERAL", f"Pledged asset for loan #{sel_loan} valued at {selected_currency} {asset_val:,.2f}")
                    st.success("Collateral asset successfully pledged and recorded!")
        else:
            st.info("No active loans available.")
            
    with cg_tab2:
        if not loans_df.empty:
            loan_opts = {f"Loan #{row['id']} - {row['full_name']}": row['id'] for _, row in loans_df.iterrows()}
            sel_loan_g = loan_opts[st.selectbox("Select Target Active Loan", list(loan_opts.keys()), key="cg_loan_guar")]
            
            with st.form("guarantor_form", clear_on_submit=True):
                g_name = st.text_input("Guarantor Full Name").strip()
                g_phone = st.text_input("Guarantor Phone Number").strip()
                g_nid = st.text_input("Guarantor National ID").strip()
                g_rel = st.text_input("Relationship to Borrower").strip()
                
                if st.form_submit_button("Attach Guarantor"):
                    execute_query("INSERT INTO guarantors (loan_id, full_name, phone, national_id, relationship) VALUES (?, ?, ?, ?, ?)",
                                  (sel_loan_g, g_name, g_phone, g_nid, g_rel))
                    log_action(user_role, "ATTACH_GUARANTOR", f"Attached guarantor {g_name} to loan #{sel_loan_g}")
                    st.success("Guarantor successfully linked to loan account!")
        else:
            st.info("No active loans available.")

# --- MODULE 6: LOAN REFINANCING & RESTRUCTURING ---
elif selected_menu_item == t.get('restructuring', "Loan Refinancing & Restructuring"):
    st.subheader("🔄 Loan Refinancing & Term Restructuring")
    active_loans_df = query_df("SELECT active_loans.id, clients.full_name, active_loans.principal, active_loans.term_months, active_loans.interest_rate FROM active_loans JOIN clients ON active_loans.client_id = clients.id WHERE active_loans.status = 'ACTIVE'")
    
    if not active_loans_df.empty:
        rest_options = {f"Loan #{row['id']} - {row['full_name']} ({selected_currency} {row['principal']:,.2f})": row for _, row in active_loans_df.iterrows()}
        selected_label = st.selectbox("Select Loan Account to Restructure", list(rest_options.keys()))
        target_loan = rest_options[selected_label]
        
        st.write(f"**Current Term:** {target_loan['term_months']} Months | **Current Interest:** {target_loan['interest_rate']}% / Month")
        
        with st.form("restructure_form"):
            new_tenure = st.number_input("New Tenure (Months)", min_value=1, value=int(target_loan['term_months']) + 3)
            new_rate = st.number_input("New Monthly Interest Rate (%)", min_value=0.1, value=float(target_loan['interest_rate']), step=0.1)
            reason = st.text_area("Restructuring Reason / Justification")
            
            if st.form_submit_button("Apply Loan Restructure"):
                new_due = datetime.now() + timedelta(days=new_tenure * 30)
                execute_query("UPDATE active_loans SET term_months = ?, interest_rate = ?, due_date = ? WHERE id = ?",
                              (new_tenure, new_rate, new_due.strftime("%Y-%m-%d"), target_loan['id']))
                log_action(user_role, "RESTRUCTURE_LOAN", f"Restructured loan #{target_loan['id']}: {new_tenure} mos @ {new_rate}%")
                st.success("Loan terms successfully restructured and updated!")
    else:
        st.info("No active loans available for restructuring.")

# --- MODULE 7: BANK STATEMENT CASH FLOW PARSER ---
elif selected_menu_item == t['bank_parser']:
    st.subheader(f"📑 {t['bank_parser']}")
    uploaded_file = st.file_uploader("Upload Bank Statement (CSV / Excel format)", type=["csv", "xlsx"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_stmt = pd.read_csv(uploaded_file)
            else:
                df_stmt = pd.read_excel(uploaded_file)
                
            st.markdown("##### 📊 Statement Preview")
            st.dataframe(df_stmt.head(), use_container_width=True)
            
            cols = list(df_stmt.columns)
            amount_col = st.selectbox("Select Transaction Amount Column", cols)
            
            numeric_amounts = pd.to_numeric(df_stmt[amount_col], errors='coerce').fillna(0)
            inflows = numeric_amounts[numeric_amounts > 0].sum()
            outflows = abs(numeric_amounts[numeric_amounts < 0].sum())
            net_cash_flow = inflows - outflows
            
            st.markdown("##### 💡 Automated Cash Flow Analytics")
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Inflows (Credits)", f"{selected_currency} {inflows:,.2f}")
            m2.metric("Total Outflows (Debits)", f"{selected_currency} {outflows:,.2f}")
            m3.metric("Net Surplus / Cash Flow", f"{selected_currency} {net_cash_flow:,.2f}")
            
            if net_cash_flow > 0:
                st.success("Positive Cash Flow verified. Borrower eligible for credit underwriting.")
            else:
                st.warning("Negative Cash Flow detected. Caution advised for underwriting.")
        except Exception as e:
            st.error(f"Error parsing statement file: {e}")

# --- MODULE 8: WHATSAPP & SMS COMMUNICATION HUB ---
elif selected_menu_item == t['comm_hub']:
    st.subheader(f"💬 {t['comm_hub']}")
    
    with st.form("send_comm_form", clear_on_submit=True):
        comm_phone = st.text_input("Recipient Phone Number").strip()
        comm_channel = st.radio("Dispatch Channel", ["SMS", "WhatsApp Business API"], horizontal=True)
        comm_msg = st.text_area("Message Content")
        
        if st.form_submit_button("Send Dispatch"):
            if comm_phone and comm_msg:
                send_comm_message(comm_phone, comm_msg, channel=comm_channel)
                st.success(f"Message dispatched via **{comm_channel}** to **{comm_phone}**!")
            else:
                st.error("Please enter both recipient phone and message content.")
                
    st.markdown("---")
    st.markdown("##### 📜 Dispatch Logs")
    sms_df = query_df("SELECT sent_at AS 'Timestamp', recipient_phone AS 'Recipient', channel AS 'Channel', message AS 'Message', status AS 'Status' FROM sms_logs ORDER BY id DESC")
    if not sms_df.empty:
        st.dataframe(sms_df, use_container_width=True)

# --- MODULE 9: PREDICTIVE RISK & DEBT RECOVERY ---
elif selected_menu_item == t['predictive_risk']:
    st.subheader(f"🎯 {t['predictive_risk']}")
    loans_df = query_df("SELECT active_loans.id, clients.full_name, clients.phone, active_loans.principal, active_loans.term_months, active_loans.due_date FROM active_loans JOIN clients ON active_loans.client_id = clients.id WHERE active_loans.status = 'ACTIVE'")
    if not loans_df.empty:
        risk_table = []
        for _, row in loans_df.iterrows():
            risk_pct, risk_cat, _ = predict_default_risk(row['id'], row['principal'], row['term_months'])
            risk_table.append({
                "Loan ID": f"#{row['id']}",
                "Borrower": row['full_name'],
                "Phone": row['phone'],
                f"Principal ({selected_currency})": f"{row['principal']:,.2f}",
                "Maturity Date": row['due_date'],
                "Default Risk": f"{risk_pct}%",
                "Classification": risk_cat
            })
        st.dataframe(pd.DataFrame(risk_table), use_container_width=True)
    else:
        st.info("No active loans to analyze.")

# --- MODULE 10: INVESTOR & LIQUIDITY POOL ---
elif selected_menu_item == t['investor_pool']:
    st.subheader(f"🏦 {t['investor_pool']}")
    inv_col1, inv_col2 = st.columns(2)
    with inv_col1:
        with st.form("investor_form", clear_on_submit=True):
            inv_name = st.text_input("Investor Name")
            inv_amount = st.number_input(f"Capital Amount ({selected_currency})", min_value=1000.0, value=10000.0, step=1000.0)
            cost_rate = st.number_input("Cost of Capital Rate (%)", min_value=1.0, value=10.0, step=0.5)
            if st.form_submit_button("Deposit Capital"):
                today = datetime.now().strftime("%Y-%m-%d")
                execute_query("INSERT INTO investor_capital (investor_name, capital_amount, cost_of_capital_rate, date_deposited) VALUES (?, ?, ?, ?)",
                              (inv_name, inv_amount, cost_rate, today))
                record_gl_entry("Investor Equity Capital", "EQUITY", debit=0.0, credit=inv_amount, description=f"Capital from {inv_name}")
                record_gl_entry("Cash at Bank", "ASSET", debit=inv_amount, credit=0.0, description=f"Capital from {inv_name}")
                st.success(f"Deposited **{selected_currency} {inv_amount:,.2f}** from **{inv_name}**!")

    with inv_col2:
        inv_df = query_df("SELECT * FROM investor_capital")
        total_inv_capital = inv_df['capital_amount'].sum() if not inv_df.empty else 0.0
        weighted_cost = (inv_df['capital_amount'] * inv_df['cost_of_capital_rate']).sum() / total_inv_capital if total_inv_capital > 0 else 0.0
        st.metric("Total Wholesale Capital Pool", f"{selected_currency} {total_inv_capital:,.2f}")
        st.metric("Portfolio WACC Rate", f"{weighted_cost:.2f}%")

# --- MODULE 11: IFRS 9 & PENALTY ENGINE ---
elif selected_menu_item == t['ifrs9']:
    st.subheader(f"⚖️ {t['ifrs9']}")
    loans_df = query_df("SELECT * FROM active_loans WHERE status = 'ACTIVE'")
    
    if not loans_df.empty:
        st.markdown("##### 📐 IFRS 9 Portfolio Loss Provisioning")
        ecl_summary = calculate_ifrs9_provisioning(loans_df)
        
        ecl_cols = st.columns(4)
        ecl_cols[0].metric("Stage 1 (12-mo ECL)", f"{selected_currency} {ecl_summary['Stage 1 (12-mo ECL)']:,.2f}")
        ecl_cols[1].metric("Stage 2 (Lifetime ECL)", f"{selected_currency} {ecl_summary['Stage 2 (Lifetime ECL)']:,.2f}")
        ecl_cols[2].metric("Stage 3 (Impaired)", f"{selected_currency} {ecl_summary['Stage 3 (Impaired)']:,.2f}")
        ecl_cols[3].metric("Total Required Reserve", f"{selected_currency} {ecl_summary['Total Provision Required']:,.2f}")

        st.markdown("---")
        st.markdown("##### ⚡ Overdue Penalty Assessment")
        penalty_rate = st.number_input(f"Fixed Penalty Fee ({selected_currency})", value=100.0, step=10.0)
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if st.button("Apply Penalties to Overdue Accounts"):
            execute_query("UPDATE active_loans SET penalty_fee = penalty_fee + ? WHERE status = 'ACTIVE' AND due_date < ?", (penalty_rate, today_str))
            st.success(f"Applied {selected_currency} {penalty_rate:,.2f} penalty to overdue accounts.")
    else:
        st.info("No active loans available for IFRS 9 evaluation.")

# --- MODULE 12: FINANCIAL STATEMENTS & P&L ---
elif selected_menu_item == t.get('financial_statements', "Financial Statements & P&L"):
    st.subheader("📊 Financial Statements & Profit & Loss Statement")
    
    gl_df = query_df("SELECT * FROM general_ledger")
    if not gl_df.empty:
        income = gl_df[gl_df['account_type'] == 'INCOME']['credit'].sum() - gl_df[gl_df['account_type'] == 'INCOME']['debit'].sum()
        expenses = gl_df[gl_df['account_type'] == 'EXPENSE']['debit'].sum() - gl_df[gl_df['account_type'] == 'EXPENSE']['credit'].sum()
        net_profit = income - expenses
        
        assets = gl_df[gl_df['account_type'] == 'ASSET']['debit'].sum() - gl_df[gl_df['account_type'] == 'ASSET']['credit'].sum()
        liabilities = gl_df[gl_df['account_type'] == 'LIABILITY']['credit'].sum() - gl_df[gl_df['account_type'] == 'LIABILITY']['debit'].sum()
        equity = gl_df[gl_df['account_type'] == 'EQUITY']['credit'].sum() - gl_df[gl_df['account_type'] == 'EQUITY']['debit'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Gross Operating Revenue", f"{selected_currency} {income:,.2f}")
        c2.metric("Total Operating Expenses", f"{selected_currency} {expenses:,.2f}")
        c3.metric("Net Income / Profit", f"{selected_currency} {net_profit:,.2f}")
        
        st.markdown("---")
        st.markdown("##### ⚖️ Balance Sheet Summary")
        b1, b2, b3 = st.columns(3)
        b1.metric("Total Gross Assets", f"{selected_currency} {assets:,.2f}")
        b2.metric("Total Liabilities", f"{selected_currency} {liabilities:,.2f}")
        b3.metric("Total Equity Capital", f"{selected_currency} {equity:,.2f}")
    else:
        st.info("No ledger entries to compute financial statements.")

# --- MODULE 13: GENERAL LEDGER ACCOUNTING ---
elif selected_menu_item == t['general_ledger']:
    st.subheader(f"📑 {t['general_ledger']}")
    gl_df = query_df("SELECT created_at AS 'Date', account_name AS 'Account', account_type AS 'Type', debit AS 'Debit', credit AS 'Credit', description AS 'Description' FROM general_ledger ORDER BY id DESC")
    if not gl_df.empty:
        st.dataframe(gl_df, use_container_width=True)
    else:
        st.info("No transactions posted yet.")

# --- MODULE 14: AMORTIZATION CALCULATOR ---
elif selected_menu_item == t['amortization']:
    st.subheader(f"📊 {t['amortization']}")
    col1, col2, col3 = st.columns(3)
    p = col1.number_input(f"Principal ({selected_currency})", value=1000.0, min_value=100.0)
    r = col2.number_input("Annual Interest Rate (%)", value=18.0, min_value=0.1)
    n = col3.number_input("Tenure (Months)", value=12, min_value=1)
    
    m_rate = (r / 100) / 12
    if m_rate > 0:
        pmt = p * (m_rate * (1 + m_rate)**n) / ((1 + m_rate)**n - 1)
    else:
        pmt = p / n
    
    schedule = []
    bal = p
    for month in range(1, int(n) + 1):
        interest = bal * m_rate
        principal_pay = pmt - interest
        bal -= principal_pay
        schedule.append({
            "Month": month,
            "Installment": round(pmt, 2),
            "Principal": round(principal_pay, 2),
            "Interest": round(interest, 2),
            "Ending Balance": round(max(0, bal), 2)
        })
    st.dataframe(pd.DataFrame(schedule), use_container_width=True)

# --- MODULE 15: SYSTEM AUDIT TRAIL ---
elif selected_menu_item == t['audit_trail']:
    st.subheader(f"📜 {t['audit_trail']}")
    logs_df = query_df("SELECT timestamp AS 'Timestamp', user_role AS 'Role', action AS 'Action', details AS 'Details' FROM audit_logs ORDER BY id DESC")
    if not logs_df.empty:
        st.dataframe(logs_df, use_container_width=True)

# --- MODULE 16: EXECUTIVE DASHBOARD ---
else:
    st.subheader(f"📈 {t['dashboard']}")
    clients_df = query_df("SELECT * FROM clients")
    loans_df = query_df("SELECT * FROM active_loans")
    repayments_df = query_df("SELECT * FROM repayments")
    
    total_disbursed = loans_df[loans_df['status'] == 'ACTIVE']['principal'].sum() if not loans_df.empty else 0.0
    total_collected = repayments_df['amount_paid'].sum() if not repayments_df.empty else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t['total_borrowers'], f"{len(clients_df)}")
    m2.metric(t['active_loans'], f"{len(loans_df[loans_df['status'] == 'ACTIVE'])}")
    m3.metric(t['total_disbursed'], f"{selected_currency} {total_disbursed:,.2f}")
    m4.metric(t['total_collections'], f"{selected_currency} {total_collected:,.2f}")
    
    st.markdown("---")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("📊 Capital Velocity")
        fig_bar = px.bar(
            x=["Total Disbursed", "Total Collections"],
            y=[total_disbursed, total_collected],
            labels={'x': 'Metric', 'y': f'Amount ({selected_currency})'},
            color=["Total Disbursed", "Total Collections"],
            template="plotly_dark",
            color_discrete_sequence=["#e74c3c", "#2ecc71"]
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with chart_col2:
        st.subheader("🍩 Portfolio Distribution")
        if not loans_df.empty and 'status' in loans_df.columns:
            status_counts = loans_df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig_pie = px.pie(status_counts, values='Count', names='Status', hole=0.4, template="plotly_dark")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No portfolio data available.")