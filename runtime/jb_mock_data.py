"""Mock data for UI development. Returns realistic fake data for all API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import random

def _now():
    return datetime.now(timezone.utc)

def _ago(minutes=0, seconds=0):
    return (_now() - timedelta(minutes=minutes, seconds=seconds)).isoformat()

def _duration(minutes=0, seconds=0):
    return int(timedelta(minutes=minutes, seconds=seconds).total_seconds())

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------

WS1_ID = "mock-ws-personal"
WS2_ID = "mock-ws-trading"

MISSION_CHAT_1 = "mock-m-chat-1"
MISSION_GMAIL = "mock-m-gmail"
MISSION_NEWS = "mock-m-news"
MISSION_EXPENSE = "mock-m-expense"
MISSION_CHAT_2 = "mock-m-chat-2"
MISSION_BTC = "mock-m-btc"

# Component IDs — Gmail pipeline
COMP_GMAIL_CONNECTOR = "mock-c-gmail-connector"
COMP_EMAIL_FILTER = "mock-c-email-filter"
COMP_TELEGRAM_SENDER = "mock-c-telegram-sender"

# Component IDs — News Digest (building)
COMP_RSS_FETCHER = "mock-c-rss-fetcher"
COMP_CONTENT_SUMMARIZER = "mock-c-content-summarizer"
COMP_SLACK_POSTER = "mock-c-slack-poster"
COMP_NEWS_SCHEDULER = "mock-c-news-scheduler"

# Component IDs — Expense Tracker (planning)
COMP_BANK_API = "mock-c-bank-api"
COMP_CATEGORIZER = "mock-c-categorizer"
COMP_DASHBOARD_GEN = "mock-c-dashboard-gen"
COMP_GSHEETS = "mock-c-gsheets"

# Component IDs — BTC Alert
COMP_COINGECKO = "mock-c-coingecko"
COMP_PRICE_THRESHOLD = "mock-c-price-threshold"
COMP_SMS_SENDER = "mock-c-sms-sender"

# Task IDs
TASK_GMAIL_1 = "mock-t-gmail-1"
TASK_GMAIL_2 = "mock-t-gmail-2"
TASK_GMAIL_3 = "mock-t-gmail-3"
TASK_NEWS_1 = "mock-t-news-1"
TASK_NEWS_2 = "mock-t-news-2"
TASK_NEWS_3 = "mock-t-news-3"
TASK_NEWS_4 = "mock-t-news-4"
TASK_NEWS_5 = "mock-t-news-5"
TASK_NEWS_6 = "mock-t-news-6"
TASK_BTC_1 = "mock-t-btc-1"
TASK_BTC_2 = "mock-t-btc-2"
TASK_BTC_3 = "mock-t-btc-3"

# Service IDs
SVC_GMAIL = "mock-svc-gmail"
SVC_BTC = "mock-svc-btc"

# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

def get_workspaces():
    return [
        {
            "id": WS1_ID,
            "name": "Personal Automation",
            "description": "Automates repetitive work tasks — email monitoring, notifications, and reporting",
            "status": "active",
            "stage": "building",
            "focused_mission_id": MISSION_NEWS,
            "mission_count": 4,
            "component_count": 11,
            "active_task_count": 1,
            "total_task_count": 15,
            "mission_ids": [MISSION_CHAT_1, MISSION_GMAIL, MISSION_NEWS, MISSION_EXPENSE],
            "session_key": f"agent:main:jbcp-frontend:company:{WS1_ID}",
            "created_at": _ago(minutes=1440),
            "updated_at": _ago(minutes=5),
        },
        {
            "id": WS2_ID,
            "name": "Trading Tools",
            "description": "Automated trading signals, price monitoring, and portfolio analysis.",
            "status": "active",
            "stage": "production",
            "focused_mission_id": MISSION_BTC,
            "mission_count": 2,
            "component_count": 3,
            "active_task_count": 0,
            "total_task_count": 5,
            "mission_ids": [MISSION_CHAT_2, MISSION_BTC],
            "session_key": f"agent:main:jbcp-frontend:company:{WS2_ID}",
            "created_at": _ago(minutes=2880),
            "updated_at": _ago(minutes=30),
        },
    ]


# ---------------------------------------------------------------------------
# Missions
# ---------------------------------------------------------------------------

_ALL_MISSIONS = None

def _build_missions():
    global _ALL_MISSIONS
    if _ALL_MISSIONS is not None:
        return _ALL_MISSIONS

    _ALL_MISSIONS = [
        # WS1: Chat
        {
            "id": MISSION_CHAT_1,
            "mission_id": MISSION_CHAT_1,
            "company_id": WS1_ID,
            "name": "General workspace chat",
            "goal": "General workspace chat",
            "status": "active",
            "items": [],
            "components": [],
            "connections": [],
            "created_at": _ago(minutes=1440),
            "updated_at": _ago(minutes=60),
        },
        # WS1: Gmail Email Alert Pipeline (complete, live)
        {
            "id": MISSION_GMAIL,
            "mission_id": MISSION_GMAIL,
            "company_id": WS1_ID,
            "name": "Gmail Email Alert Pipeline",
            "goal": "Build a Gmail email alert pipeline that checks for important emails and forwards summaries to Telegram",
            "status": "active",
            "items": [
                {"goal": "Build Gmail API connector with OAuth2 authentication", "type": "component", "component_name": "Gmail Connector", "status": "complete"},
                {"goal": "Build email filter with configurable rules (sender, subject, labels)", "type": "component", "component_name": "Email Filter", "status": "complete"},
                {"goal": "Build Telegram bot sender for formatted email summaries", "type": "component", "component_name": "Telegram Sender", "status": "complete"},
            ],
            "components": [
                {"name": "Gmail Connector", "type": "connector", "description": "Connects to Gmail API via OAuth2, fetches unread emails since last check", "status": "built"},
                {"name": "Email Filter", "type": "processor", "description": "Filters emails by configurable rules: sender whitelist, subject keywords, labels", "status": "built"},
                {"name": "Telegram Sender", "type": "output", "description": "Formats email summaries and sends to Telegram chat via Bot API", "status": "built"},
            ],
            "connections": [
                {"from": "Gmail Connector", "to": "Email Filter", "label": "raw emails"},
                {"from": "Email Filter", "to": "Telegram Sender", "label": "filtered emails"},
            ],
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=120),
        },
        # WS1: Daily News Digest (building)
        {
            "id": MISSION_NEWS,
            "mission_id": MISSION_NEWS,
            "company_id": WS1_ID,
            "name": "Daily News Digest",
            "goal": "Build a daily news digest that fetches RSS feeds, summarizes articles with AI, and posts to Slack",
            "status": "active",
            "items": [
                {"goal": "Build RSS feed fetcher with multi-source support", "type": "component", "component_name": "RSS Fetcher", "status": "complete"},
                {"goal": "Build AI content summarizer using Claude API", "type": "component", "component_name": "Content Summarizer", "status": "in_progress"},
                {"goal": "Build Slack poster with rich formatting", "type": "component", "component_name": "Slack Poster", "status": "planned"},
                {"goal": "Build scheduler for daily digest timing", "type": "component", "component_name": "Scheduler", "status": "planned"},
                {"goal": "Write integration tests for the full pipeline", "type": "task", "status": "planned"},
                {"goal": "Configure RSS feed sources and Slack webhook", "type": "task", "status": "planned"},
            ],
            "components": [
                {"name": "RSS Fetcher", "type": "connector", "description": "Fetches and parses RSS/Atom feeds from multiple configured sources", "status": "built"},
                {"name": "Content Summarizer", "type": "ai", "description": "Uses Claude API to generate concise summaries of news articles", "status": "building"},
                {"name": "Slack Poster", "type": "output", "description": "Posts formatted digest to Slack channel via webhook with rich blocks", "status": "planned"},
                {"name": "Scheduler", "type": "scheduler", "description": "Cron-based scheduler that triggers the digest pipeline at configured times", "status": "planned"},
            ],
            "connections": [
                {"from": "RSS Fetcher", "to": "Content Summarizer", "label": "raw articles"},
                {"from": "Content Summarizer", "to": "Slack Poster", "label": "summaries"},
                {"from": "Scheduler", "to": "RSS Fetcher", "label": "trigger"},
            ],
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=2),
        },
        # WS1: Expense Tracker (planning)
        {
            "id": MISSION_EXPENSE,
            "mission_id": MISSION_EXPENSE,
            "company_id": WS1_ID,
            "name": "Expense Tracker",
            "goal": "Build an expense tracker that connects to bank API, categorizes transactions, and generates a dashboard with Google Sheets export",
            "status": "planning",
            "items": [
                {"goal": "Build Plaid bank API connector for transaction fetching", "type": "component", "component_name": "Bank API Connector", "status": "planned"},
                {"goal": "Build AI transaction categorizer with custom category training", "type": "component", "component_name": "Transaction Categorizer", "status": "planned"},
                {"goal": "Build HTML dashboard generator with charts and filters", "type": "component", "component_name": "Dashboard Generator", "status": "planned"},
                {"goal": "Build Google Sheets output connector for spreadsheet export", "type": "component", "component_name": "Google Sheets Output", "status": "planned"},
                {"goal": "Write end-to-end tests with mock bank data", "type": "task", "status": "planned"},
                {"goal": "Create deployment configuration and environment setup script", "type": "task", "status": "planned"},
            ],
            "components": [
                {"name": "Bank API Connector", "type": "connector", "description": "Connects to Plaid API to fetch recent transactions with pagination", "status": "planned"},
                {"name": "Transaction Categorizer", "type": "ai", "description": "AI-powered transaction categorizer with customizable categories and learning", "status": "planned"},
                {"name": "Dashboard Generator", "type": "output", "description": "Generates interactive HTML dashboard with spending charts, trends, and filters", "status": "planned"},
                {"name": "Google Sheets Output", "type": "output", "description": "Exports categorized transactions to Google Sheets with auto-formatting", "status": "planned"},
            ],
            "connections": [
                {"from": "Bank API Connector", "to": "Transaction Categorizer", "label": "raw transactions"},
                {"from": "Transaction Categorizer", "to": "Dashboard Generator", "label": "categorized data"},
                {"from": "Transaction Categorizer", "to": "Google Sheets Output", "label": "categorized data"},
            ],
            "created_at": _ago(minutes=45),
            "updated_at": _ago(minutes=10),
        },
        # WS2: Chat
        {
            "id": MISSION_CHAT_2,
            "mission_id": MISSION_CHAT_2,
            "company_id": WS2_ID,
            "name": "General workspace chat",
            "goal": "General workspace chat",
            "status": "active",
            "items": [],
            "components": [],
            "connections": [],
            "created_at": _ago(minutes=2880),
            "updated_at": _ago(minutes=120),
        },
        # WS2: BTC Price Alert (live)
        {
            "id": MISSION_BTC,
            "mission_id": MISSION_BTC,
            "company_id": WS2_ID,
            "name": "BTC Price Alert",
            "goal": "Build a BTC price alert that checks CoinGecko every minute and sends SMS when price crosses thresholds",
            "status": "active",
            "items": [
                {"goal": "Build CoinGecko API fetcher for BTC price data", "type": "component", "component_name": "CoinGecko Fetcher", "status": "complete"},
                {"goal": "Build price threshold checker with configurable alerts", "type": "component", "component_name": "Price Threshold", "status": "complete"},
                {"goal": "Build Twilio SMS sender for price alerts", "type": "component", "component_name": "SMS Sender", "status": "complete"},
            ],
            "components": [
                {"name": "CoinGecko Fetcher", "type": "connector", "description": "Fetches current BTC/USD price from CoinGecko public API", "status": "built"},
                {"name": "Price Threshold", "type": "processor", "description": "Checks price against configurable upper/lower thresholds with cooldown", "status": "built"},
                {"name": "SMS Sender", "type": "output", "description": "Sends SMS alerts via Twilio API with price and direction info", "status": "built"},
            ],
            "connections": [
                {"from": "CoinGecko Fetcher", "to": "Price Threshold", "label": "price data"},
                {"from": "Price Threshold", "to": "SMS Sender", "label": "threshold alerts"},
            ],
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=30),
        },
    ]
    return _ALL_MISSIONS


# ---------------------------------------------------------------------------
# Components (full detail)
# ---------------------------------------------------------------------------

def _all_components():
    return [
        # Gmail pipeline
        {
            "id": COMP_GMAIL_CONNECTOR,
            "component_id": COMP_GMAIL_CONNECTOR,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "name": "Gmail Connector",
            "type": "connector",
            "description": "Connects to Gmail API via OAuth2, fetches unread emails since last check",
            "status": "built",
            "input_type": "trigger",
            "output_type": "email_list",
            "config_fields": ["credentials_path", "poll_interval_sec", "max_results"],
            "input_schema": {"type": "object", "properties": {"trigger": {"type": "string"}}},
            "output_schema": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "from": {"type": "string"}, "subject": {"type": "string"}, "snippet": {"type": "string"}, "date": {"type": "string"}}}, "properties": {"summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 187,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1100),
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1100),
        },
        {
            "id": COMP_EMAIL_FILTER,
            "component_id": COMP_EMAIL_FILTER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "name": "Email Filter",
            "type": "processor",
            "description": "Filters emails by configurable rules: sender whitelist, subject keywords, Gmail labels",
            "status": "built",
            "input_type": "email_list",
            "output_type": "email_list",
            "config_fields": ["sender_whitelist", "subject_keywords", "label_filter", "min_importance"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "array", "items": {"type": "object"}, "properties": {"summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 124,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1050),
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1050),
        },
        {
            "id": COMP_TELEGRAM_SENDER,
            "component_id": COMP_TELEGRAM_SENDER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "name": "Telegram Sender",
            "type": "output",
            "description": "Formats email summaries into Telegram messages and sends via Bot API",
            "status": "built",
            "input_type": "email_list",
            "output_type": "notification",
            "config_fields": ["bot_token", "chat_id", "parse_mode"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "object", "properties": {"sent_count": {"type": "integer"}, "errors": {"type": "array"}, "summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 98,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1000),
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1000),
        },
        # News Digest pipeline
        {
            "id": COMP_RSS_FETCHER,
            "component_id": COMP_RSS_FETCHER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "name": "RSS Fetcher",
            "type": "connector",
            "description": "Fetches and parses RSS/Atom feeds from multiple configured sources with deduplication",
            "status": "built",
            "input_type": "trigger",
            "output_type": "article_list",
            "config_fields": ["feed_urls", "max_articles_per_feed", "dedup_window_hours"],
            "input_schema": {"type": "object", "properties": {"trigger": {"type": "string"}}},
            "output_schema": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "content": {"type": "string"}, "source": {"type": "string"}, "published": {"type": "string"}}}},
            "line_count": 215,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=60),
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=60),
        },
        {
            "id": COMP_CONTENT_SUMMARIZER,
            "component_id": COMP_CONTENT_SUMMARIZER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "name": "Content Summarizer",
            "type": "ai",
            "description": "Uses Claude API to generate concise 2-3 sentence summaries of news articles with key takeaways",
            "status": "building",
            "input_type": "article_list",
            "output_type": "summary_list",
            "config_fields": ["model", "max_tokens", "summary_style", "include_sentiment"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "summary": {"type": "string"}, "sentiment": {"type": "string"}, "key_topics": {"type": "array"}}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=3),
        },
        {
            "id": COMP_SLACK_POSTER,
            "component_id": COMP_SLACK_POSTER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "name": "Slack Poster",
            "type": "output",
            "description": "Posts formatted news digest to Slack channel via webhook using rich Block Kit formatting",
            "status": "planned",
            "input_type": "summary_list",
            "output_type": "notification",
            "config_fields": ["webhook_url", "channel", "bot_name", "bot_icon"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "object", "properties": {"posted": {"type": "boolean"}, "message_ts": {"type": "string"}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        {
            "id": COMP_NEWS_SCHEDULER,
            "component_id": COMP_NEWS_SCHEDULER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "name": "Scheduler",
            "type": "scheduler",
            "description": "Cron-based scheduler that triggers the digest pipeline at configured times (default 8am daily)",
            "status": "planned",
            "input_type": "cron",
            "output_type": "trigger",
            "config_fields": ["cron_expression", "timezone", "enabled"],
            "input_schema": {"type": "object", "properties": {"cron": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"trigger": {"type": "string"}, "scheduled_time": {"type": "string"}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        # Expense Tracker (all planned)
        {
            "id": COMP_BANK_API,
            "component_id": COMP_BANK_API,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_EXPENSE,
            "name": "Bank API Connector",
            "type": "connector",
            "description": "Connects to Plaid API to fetch recent transactions with pagination and account linking",
            "status": "planned",
            "input_type": "trigger",
            "output_type": "transaction_list",
            "config_fields": ["plaid_client_id", "plaid_secret", "access_token", "account_ids"],
            "input_schema": {"type": "object", "properties": {"trigger": {"type": "string"}, "start_date": {"type": "string"}, "end_date": {"type": "string"}}},
            "output_schema": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "amount": {"type": "number"}, "merchant": {"type": "string"}, "date": {"type": "string"}, "category": {"type": "array"}}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=45),
            "updated_at": _ago(minutes=45),
        },
        {
            "id": COMP_CATEGORIZER,
            "component_id": COMP_CATEGORIZER,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_EXPENSE,
            "name": "Transaction Categorizer",
            "type": "ai",
            "description": "AI-powered transaction categorizer with customizable categories and continuous learning from corrections",
            "status": "planned",
            "input_type": "transaction_list",
            "output_type": "categorized_transactions",
            "config_fields": ["categories", "model", "confidence_threshold", "learn_from_corrections"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "amount": {"type": "number"}, "category": {"type": "string"}, "confidence": {"type": "number"}}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=45),
            "updated_at": _ago(minutes=45),
        },
        {
            "id": COMP_DASHBOARD_GEN,
            "component_id": COMP_DASHBOARD_GEN,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_EXPENSE,
            "name": "Dashboard Generator",
            "type": "output",
            "description": "Generates interactive HTML dashboard with spending charts, monthly trends, and category breakdowns",
            "status": "planned",
            "input_type": "categorized_transactions",
            "output_type": "html_report",
            "config_fields": ["template", "chart_library", "date_range", "currency"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "object", "properties": {"html": {"type": "string"}, "charts": {"type": "array"}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=45),
            "updated_at": _ago(minutes=45),
        },
        {
            "id": COMP_GSHEETS,
            "component_id": COMP_GSHEETS,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_EXPENSE,
            "name": "Google Sheets Output",
            "type": "output",
            "description": "Exports categorized transactions to Google Sheets with auto-formatting, formulas, and pivot tables",
            "status": "planned",
            "input_type": "categorized_transactions",
            "output_type": "spreadsheet",
            "config_fields": ["credentials_path", "spreadsheet_id", "sheet_name", "auto_format"],
            "input_schema": {"type": "array", "items": {"type": "object"}},
            "output_schema": {"type": "object", "properties": {"spreadsheet_url": {"type": "string"}, "rows_written": {"type": "integer"}}},
            "line_count": 0,
            "built_by": None,
            "built_at": None,
            "created_at": _ago(minutes=45),
            "updated_at": _ago(minutes=45),
        },
        # BTC Alert pipeline
        {
            "id": COMP_COINGECKO,
            "component_id": COMP_COINGECKO,
            "workspace_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "name": "CoinGecko Fetcher",
            "type": "connector",
            "description": "Fetches current BTC/USD price from CoinGecko public API with rate limiting",
            "status": "built",
            "input_type": "trigger",
            "output_type": "price_data",
            "config_fields": ["coin_id", "vs_currency", "rate_limit_ms"],
            "input_schema": {"type": "object", "properties": {"trigger": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"price_usd": {"type": "number"}, "market_cap": {"type": "number"}, "volume_24h": {"type": "number"}, "change_24h": {"type": "number"}, "timestamp": {"type": "string"}, "summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 76,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1800),
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1800),
        },
        {
            "id": COMP_PRICE_THRESHOLD,
            "component_id": COMP_PRICE_THRESHOLD,
            "workspace_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "name": "Price Threshold",
            "type": "processor",
            "description": "Checks BTC price against configurable upper/lower thresholds with cooldown to prevent alert spam",
            "status": "built",
            "input_type": "price_data",
            "output_type": "alert",
            "config_fields": ["upper_threshold", "lower_threshold", "cooldown_minutes", "alert_on_recovery"],
            "input_schema": {"type": "object", "properties": {"price_usd": {"type": "number"}}},
            "output_schema": {"type": "object", "properties": {"triggered": {"type": "boolean"}, "direction": {"type": "string"}, "price": {"type": "number"}, "threshold": {"type": "number"}, "summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 93,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1750),
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1750),
        },
        {
            "id": COMP_SMS_SENDER,
            "component_id": COMP_SMS_SENDER,
            "workspace_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "name": "SMS Sender",
            "type": "output",
            "description": "Sends SMS alerts via Twilio API with formatted price and direction info",
            "status": "built",
            "input_type": "alert",
            "output_type": "notification",
            "config_fields": ["twilio_sid", "twilio_token", "from_number", "to_number"],
            "input_schema": {"type": "object", "properties": {"triggered": {"type": "boolean"}, "direction": {"type": "string"}, "price": {"type": "number"}}},
            "output_schema": {"type": "object", "properties": {"sent": {"type": "boolean"}, "message_sid": {"type": "string"}, "summary": {"type": "string", "description": "Human-readable summary of this output"}}},
            "line_count": 64,
            "built_by": "jbcp-worker",
            "built_at": _ago(minutes=1700),
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1700),
        },
    ]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _all_tasks():
    return [
        # Gmail pipeline tasks (all complete)
        {
            "id": TASK_GMAIL_1,
            "company_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "type": "component",
            "status": "complete",
            "priority": 1,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_GMAIL},
            "delivery": {"type": "component", "component_id": COMP_GMAIL_CONNECTOR},
            "external_process": None,
            "payload": {
                "goal": "Implement Gmail API connector with OAuth2 authentication flow and email fetching",
                "component": "Gmail Connector",
                "component_id": COMP_GMAIL_CONNECTOR,
                "result_summary": "Built gmail_connector.py with OAuth2 flow, email fetching, and pagination support. 187 lines.",
                "decisions": "Used OAuth2 for Gmail authentication (more secure, better token refresh). Implemented plain text extraction only (skipped attachments for v1 simplicity).",
            },
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1100),
        },
        {
            "id": TASK_GMAIL_2,
            "company_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "type": "component",
            "status": "complete",
            "priority": 2,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_GMAIL},
            "delivery": {"type": "component", "component_id": COMP_EMAIL_FILTER},
            "external_process": None,
            "payload": {
                "goal": "Build email filter with sender whitelist, subject keyword matching, and label-based filtering",
                "component": "Email Filter",
                "component_id": COMP_EMAIL_FILTER,
                "result_summary": "Built email_filter.py with configurable rules engine. Supports sender, subject, and label filters. 124 lines.",
                "decisions": "Used rule-based filtering over ML classification (simpler, more predictable). Chose OR logic for multiple criteria (any match passes).",
            },
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1050),
        },
        {
            "id": TASK_GMAIL_3,
            "company_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "type": "component",
            "status": "complete",
            "priority": 3,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_GMAIL},
            "delivery": {"type": "component", "component_id": COMP_TELEGRAM_SENDER},
            "external_process": None,
            "payload": {
                "goal": "Implement Telegram Bot API sender with formatted email summary messages",
                "component": "Telegram Sender",
                "component_id": COMP_TELEGRAM_SENDER,
                "result_summary": "Built telegram_sender.py with HTML formatting, error handling, and retry logic. 98 lines.",
                "decisions": "Chose HTML parse_mode for richer formatting. Added retry with exponential backoff (3 attempts max).",
            },
            "created_at": _ago(minutes=1200),
            "updated_at": _ago(minutes=1000),
        },
        # News Digest tasks (mixed states — actively building)
        {
            "id": TASK_NEWS_1,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "component",
            "status": "complete",
            "priority": 1,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "component", "component_id": COMP_RSS_FETCHER},
            "external_process": None,
            "payload": {
                "goal": "Build RSS/Atom feed fetcher with multi-source support and article deduplication",
                "component": "RSS Fetcher",
                "component_id": COMP_RSS_FETCHER,
                "result_summary": "Built rss_fetcher.py with feedparser integration, dedup by URL hash, and configurable source list. 215 lines.",
                "decisions": "Used feedparser library for broad RSS/Atom compatibility. Implemented URL-hash deduplication with 72-hour window.",
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=60),
        },
        {
            "id": TASK_NEWS_2,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "component",
            "status": "running",
            "priority": 2,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "component", "component_id": COMP_CONTENT_SUMMARIZER},
            "external_process": None,
            "payload": {
                "goal": "Implement AI content summarizer using Claude API with configurable summary length and style",
                "component": "Content Summarizer",
                "component_id": COMP_CONTENT_SUMMARIZER,
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=8),
        },
        {
            "id": TASK_NEWS_3,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "component",
            "status": "pending",
            "priority": 3,
            "assigned_to": None,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "component", "component_id": COMP_SLACK_POSTER},
            "external_process": None,
            "payload": {
                "goal": "Build Slack webhook poster with Block Kit rich formatting for news digest",
                "component": "Slack Poster",
                "component_id": COMP_SLACK_POSTER,
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        {
            "id": TASK_NEWS_4,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "component",
            "status": "pending",
            "priority": 4,
            "assigned_to": None,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "component", "component_id": COMP_NEWS_SCHEDULER},
            "external_process": None,
            "payload": {
                "goal": "Build cron-based scheduler for triggering daily digest at configurable times",
                "component": "Scheduler",
                "component_id": COMP_NEWS_SCHEDULER,
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        {
            "id": TASK_NEWS_5,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "test",
            "status": "pending",
            "priority": 5,
            "assigned_to": None,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "test"},
            "external_process": None,
            "payload": {
                "goal": "Write integration tests for the full news digest pipeline with mock feeds",
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        {
            "id": TASK_NEWS_6,
            "company_id": WS1_ID,
            "mission_id": MISSION_NEWS,
            "type": "config",
            "status": "pending",
            "priority": 6,
            "assigned_to": None,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_NEWS},
            "delivery": {"type": "config"},
            "external_process": None,
            "payload": {
                "goal": "Configure RSS feed sources (TechCrunch, HN, ArsTechnica) and set up Slack webhook",
            },
            "created_at": _ago(minutes=180),
            "updated_at": _ago(minutes=180),
        },
        # BTC Alert tasks (all complete)
        {
            "id": TASK_BTC_1,
            "company_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "type": "component",
            "status": "complete",
            "priority": 1,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_BTC},
            "delivery": {"type": "component", "component_id": COMP_COINGECKO},
            "external_process": None,
            "payload": {
                "goal": "Build CoinGecko API fetcher for real-time BTC price with rate limiting",
                "component": "CoinGecko Fetcher",
                "component_id": COMP_COINGECKO,
                "result_summary": "Built coingecko_fetcher.py with public API integration and rate limiting. 76 lines.",
                "decisions": "Used CoinGecko free API (no key required). Added 500ms rate limit to stay within free tier limits.",
            },
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1800),
        },
        {
            "id": TASK_BTC_2,
            "company_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "type": "component",
            "status": "complete",
            "priority": 2,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_BTC},
            "delivery": {"type": "component", "component_id": COMP_PRICE_THRESHOLD},
            "external_process": None,
            "payload": {
                "goal": "Implement price threshold checker with configurable bounds and cooldown logic",
                "component": "Price Threshold",
                "component_id": COMP_PRICE_THRESHOLD,
                "result_summary": "Built price_threshold.py with upper/lower bounds, cooldown tracking, and recovery alerts. 93 lines.",
                "decisions": "Added 30-minute cooldown between alerts to prevent spam. Included recovery alerts (price returning to normal range).",
            },
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1750),
        },
        {
            "id": TASK_BTC_3,
            "company_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "type": "component",
            "status": "complete",
            "priority": 3,
            "assigned_to": "jbcp-worker",
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
            "origin": {"type": "mission_plan", "mission_id": MISSION_BTC},
            "delivery": {"type": "component", "component_id": COMP_SMS_SENDER},
            "external_process": None,
            "payload": {
                "goal": "Build Twilio SMS sender for price alert notifications",
                "component": "SMS Sender",
                "component_id": COMP_SMS_SENDER,
                "result_summary": "Built sms_sender.py with Twilio integration, message formatting, and delivery confirmation. 64 lines.",
                "decisions": "Chose Twilio over SNS for better delivery tracking. Used short message format with price, direction, and threshold info.",
            },
            "created_at": _ago(minutes=2000),
            "updated_at": _ago(minutes=1700),
        },
    ]


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def get_workspace_missions(workspace_id: str):
    """Return missions for a specific workspace."""
    return [m for m in _build_missions() if m.get("company_id") == workspace_id]


def get_mission(mission_id: str):
    """Return a single mission by ID (checks both 'id' and 'mission_id')."""
    for m in _build_missions():
        if m.get("mission_id") == mission_id or m.get("id") == mission_id:
            return m
    return None


def get_mission_tasks(mission_id: str):
    """Return tasks for a specific mission."""
    return [t for t in _all_tasks() if t.get("mission_id") == mission_id]


def get_workspace_components(workspace_id: str):
    """Return all components for a workspace."""
    return [c for c in _all_components() if c.get("workspace_id") == workspace_id]


def get_workspace_graph(workspace_id: str):
    """Return graph nodes and edges for a workspace."""
    components = get_workspace_components(workspace_id)
    missions = get_workspace_missions(workspace_id)

    # Build task lookup: component_id -> list of task statuses
    all_tasks = _all_tasks()
    comp_task_statuses: dict[str, list[str]] = {}
    for t in all_tasks:
        payload = t.get("payload", {})
        cid = payload.get("component_id")
        if cid:
            comp_task_statuses.setdefault(cid, []).append(t.get("status", "unknown"))

    # Map component names to IDs
    name_to_id = {c["name"]: c["component_id"] for c in components}
    comp_by_id = {c["component_id"]: c for c in components}

    nodes = []
    for c in components:
        cid = c["component_id"]
        status = c.get("status", "planned")
        task_statuses = comp_task_statuses.get(cid, [])

        # Compute progress from tasks
        if task_statuses:
            complete_count = sum(1 for s in task_statuses if s == "complete")
            progress_percent = round(complete_count / len(task_statuses) * 100, 1)
        else:
            progress_map = {
                "planned": 0, "building": 25, "built": 50, "testing": 65,
                "passing": 85, "failing": 60, "deployed": 100,
            }
            progress_percent = progress_map.get(status, 0)

        is_active = any(s in ("running", "dispatched") for s in task_statuses)

        nodes.append({
            "id": cid,
            "label": c["name"],
            "type": c["type"],
            "status": status,
            "mission_id": c.get("mission_id"),
            "description": c.get("description", ""),
            "contract": {
                "input_type": c.get("input_type"),
                "output_type": c.get("output_type", "Any"),
                "config_fields": c.get("config_fields", []),
            },
            "is_active": is_active,
            "active_agent": None,
            "built_by": c.get("built_by"),
            "progress_percent": progress_percent,
            "display_status": {
                "planned": "Planned", "building": "Building", "built": "Built",
                "testing": "Testing", "passing": "Built", "failing": "Problem",
                "deployed": "Live",
            }.get(status, status.replace("_", " ").title()),
        })

    edges = []
    for m in missions:
        for conn in m.get("connections", []):
            from_id = name_to_id.get(conn["from"])
            to_id = name_to_id.get(conn["to"])
            if from_id and to_id:
                label = conn.get("label") or None

                # Auto-derive label from source component output_type
                if label is None:
                    source_comp = comp_by_id.get(from_id)
                    if source_comp:
                        derived = source_comp.get("output_type")
                        if derived and derived != "Any":
                            label = derived

                display_label = label.replace("_", " ").title() if label else None

                edges.append({
                    "from": from_id,
                    "to": to_id,
                    "source": from_id,
                    "target": to_id,
                    "label": label,
                    "display_label": display_label,
                })

    return {"nodes": nodes, "edges": edges}


def get_agents():
    """Return mock agent states."""
    return [
        {
            "id": "santiago-main",
            "agent_id": "santiago-main",
            "name": "Santiago",
            "model": "claude-opus-4-6",
            "status": "idle",
            "last_seen": _ago(seconds=45),
            "current_workspace": None,
            "current_label": None,
            "session_count": 47,
            "total_turns": 1283,
            "uptime_minutes": 1440,
        },
        {
            "id": "jbcp-worker-1",
            "agent_id": "jbcp-worker-1",
            "name": "JBCP Worker 1",
            "model": "claude-sonnet-4-6",
            "status": "coding",
            "last_seen": _ago(seconds=3),
            "current_workspace": WS1_ID,
            "current_label": "writing content_summarizer.py",
            "current_mission_id": MISSION_NEWS,
            "current_task_id": TASK_NEWS_2,
            "session_count": 12,
            "total_turns": 89,
            "uptime_minutes": 180,
        },
        {
            "id": "jbcp-worker-2",
            "agent_id": "jbcp-worker-2",
            "name": "JBCP Worker 2",
            "model": "claude-sonnet-4-6",
            "status": "coding",
            "last_seen": _ago(seconds=8),
            "current_workspace": WS1_ID,
            "current_label": "writing slack_poster.py",
            "current_mission_id": MISSION_NEWS,
            "current_task_id": TASK_NEWS_3,
            "session_count": 5,
            "total_turns": 34,
            "uptime_minutes": 45,
        },
        {
            "id": "jbcp-worker-3",
            "agent_id": "jbcp-worker-3",
            "name": "JBCP Worker 3",
            "model": "claude-sonnet-4-6",
            "status": "researching",
            "last_seen": _ago(seconds=15),
            "current_workspace": WS1_ID,
            "current_label": "researching Slack Block Kit API docs",
            "current_mission_id": MISSION_NEWS,
            "current_task_id": TASK_NEWS_5,
            "session_count": 3,
            "total_turns": 18,
            "uptime_minutes": 25,
        },
    ]


def get_services():
    """Return mock services."""
    return [
        {
            "id": SVC_GMAIL,
            "service_id": SVC_GMAIL,
            "workspace_id": WS1_ID,
            "mission_id": MISSION_GMAIL,
            "name": "Gmail Email Alert Pipeline",
            "description": "Checks Gmail for important emails and forwards summaries to Telegram",
            "type": "scheduled",
            "schedule": "*/5 * * * *",
            "status": "running",
            "health": "healthy",
            "port": None,
            "entry_point": "gmail_pipeline.py",
            "has_frontend": False,
            "run_count": 288,
            "last_run_at": _ago(minutes=2),
            "last_run_duration_seconds": 12,
            "last_run_status": "success",
            "last_run_summary": "Checked 47 emails, filtered 3 urgent, sent 3 Telegram alerts",
            "error_count_24h": 0,
            "run_history": [
                {
                    "run_id": "mock-run-gmail-1",
                    "started_at": _ago(minutes=2),
                    "status": "success",
                    "duration_ms": 12000,
                    "output_preview": "Checked 47 emails, filtered 3 urgent, sent 3 Telegram alerts",
                    "summary_chain": ["Fetched 47 unread emails from Gmail", "Filtered to 3 urgent (sender whitelist match)", "Sent 3 formatted alerts to Telegram"],
                },
                {
                    "run_id": "mock-run-gmail-2",
                    "started_at": _ago(minutes=7),
                    "status": "success",
                    "duration_ms": 8200,
                    "output_preview": "Checked 12 emails, 0 matched filters",
                    "summary_chain": ["Fetched 12 unread emails from Gmail", "No emails matched filter criteria", "No alerts sent"],
                },
            ],
            "created_at": _ago(minutes=960),
            "updated_at": _ago(minutes=2),
        },
        {
            "id": SVC_BTC,
            "service_id": SVC_BTC,
            "workspace_id": WS2_ID,
            "mission_id": MISSION_BTC,
            "name": "BTC Price Alert",
            "description": "Monitors BTC price and sends SMS when thresholds are crossed",
            "type": "scheduled",
            "schedule": "* * * * *",
            "status": "running",
            "health": "healthy",
            "port": None,
            "entry_point": "btc_alert.py",
            "has_frontend": False,
            "run_count": 1440,
            "last_run_at": _ago(seconds=30),
            "last_run_duration_seconds": 3,
            "last_run_status": "success",
            "last_run_summary": "BTC at $97,342 — within thresholds, no alert sent",
            "error_count_24h": 2,
            "run_history": [
                {
                    "run_id": "mock-run-btc-1",
                    "started_at": _ago(seconds=30),
                    "status": "success",
                    "duration_ms": 3000,
                    "output_preview": "BTC at $97,342 — within thresholds, no alert sent",
                    "summary_chain": ["Fetched BTC/USD: $97,342.18", "Price within $90k-$100k range", "No alert triggered"],
                },
                {
                    "run_id": "mock-run-btc-2",
                    "started_at": _ago(minutes=15),
                    "status": "success",
                    "duration_ms": 4200,
                    "output_preview": "BTC crossed $100k! SMS alert sent",
                    "summary_chain": ["Fetched BTC/USD: $100,247.55", "Upper threshold $100k breached", "SMS alert sent to +1-555-0123"],
                },
            ],
            "created_at": _ago(minutes=1680),
            "updated_at": _ago(seconds=30),
        },
    ]


def get_commands():
    """Return available commands (same structure as real)."""
    return {
        "commands": [
            {
                "name": "/mission",
                "description": "Manage missions (planning, building, tracking)",
                "subcommands": [
                    {"name": "new <goal>", "description": "Create a new mission and enter planning mode."},
                    {"name": "generate", "description": "AI generates components and tasks from the conversation."},
                    {"name": "approve", "description": "Approve the generated plan and start building."},
                    {"name": "cancel", "description": "Cancel the current mission."},
                    {"name": "list", "description": "List all missions in this workspace."},
                    {"name": "switch <name>", "description": "Switch the focused mission."},
                    {"name": "(no args)", "description": "Show current mission status."},
                ],
            },
            {
                "name": "/status",
                "description": "Quick workspace status.",
            },
        ],
        "workflow": [
            "1. /mission new <describe what you want to build>",
            "2. Chat about requirements",
            "3. /mission generate",
            "4. Review, refine, /mission generate again",
            "5. /mission approve — starts building",
        ],
    }


def get_health():
    """Return mock health data."""
    return {
        "status": "ok",
        "uptime_seconds": 86400,
        "jbcp": {
            "status": "running",
            "workspaces": 2,
            "missions": 6,
            "active_tasks": 1,
        },
        "event_bus": {
            "status": "running",
            "subscribers": 1,
            "events_emitted": 847,
        },
        "version": "0.4.0",
    }


def get_prompt_debug(workspace_id: str):
    """Return mock prompt debug tree."""
    if workspace_id == WS1_ID:
        return {
            "workspace_id": WS1_ID,
            "sections": [
                {
                    "name": "Company Context",
                    "type": "company_context",
                    "chars": 1247,
                    "preview": "Personal Automation workspace. Contains Gmail alert pipeline (live), news digest (building), and expense tracker (planning).",
                    "source": f"data/contexts/{WS1_ID}/company_context.md",
                    "injected": True,
                },
                {
                    "name": "Mission Context",
                    "type": "mission_context",
                    "mission_id": MISSION_NEWS,
                    "mission_goal": "Build a daily news digest that fetches RSS feeds, summarizes articles with AI, and posts to Slack",
                    "chars": 2834,
                    "preview": "RSS Fetcher component is complete (215 lines). Content Summarizer is currently being built by jbcp-worker. Slack Poster and Scheduler are next.",
                    "source": f"data/contexts/{WS1_ID}/{MISSION_NEWS}/mission_context.md",
                    "injected": True,
                },
                {
                    "name": "Chat History",
                    "type": "chat_history",
                    "message_count": 23,
                    "chars": None,
                    "note": "Stored in local SQLite database.",
                },
            ],
            "total_injection_chars": 4081,
            "planning_mode": False,
            "focused_mission": {
                "id": MISSION_NEWS,
                "goal": "Build a daily news digest that fetches RSS feeds, summarizes articles with AI, and posts to Slack",
                "status": "active",
            },
        }
    elif workspace_id == WS2_ID:
        return {
            "workspace_id": WS2_ID,
            "sections": [
                {
                    "name": "Company Context",
                    "type": "company_context",
                    "chars": 623,
                    "preview": "Trading Tools workspace. BTC Price Alert service is running with 1-minute checks.",
                    "source": f"data/contexts/{WS2_ID}/company_context.md",
                    "injected": True,
                },
                {
                    "name": "Mission Context",
                    "type": "mission_context",
                    "mission_id": MISSION_BTC,
                    "mission_goal": "Build a BTC price alert that checks CoinGecko every minute and sends SMS when price crosses thresholds",
                    "chars": 1456,
                    "preview": "All components built and deployed. Service running on 1-minute cron. 2 threshold alerts sent in last 24h.",
                    "source": f"data/contexts/{WS2_ID}/{MISSION_BTC}/mission_context.md",
                    "injected": True,
                },
                {
                    "name": "Chat History",
                    "type": "chat_history",
                    "message_count": 8,
                    "chars": None,
                    "note": "Stored in local SQLite database.",
                },
            ],
            "total_injection_chars": 2079,
            "planning_mode": False,
            "focused_mission": {
                "id": MISSION_BTC,
                "goal": "Build a BTC price alert that checks CoinGecko every minute and sends SMS when price crosses thresholds",
                "status": "active",
            },
        }
    return {
        "workspace_id": workspace_id,
        "sections": [],
        "total_injection_chars": 0,
        "planning_mode": False,
        "focused_mission": None,
    }


def get_recent_signals():
    """Return mock signals showing the News Digest being built (last 5 minutes)."""
    signals = []
    base = _now()

    # Simulate a building session for the Content Summarizer
    events = [
        (-290, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 4200, "label": "Planning content_summarizer.py structure"}),
        (-280, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 1800, "label": "Outlined summarizer architecture"}),
        (-270, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "search", "label": "Searching for Claude API client patterns", "args": {"query": "anthropic python client usage"}}),
        (-265, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "search", "label": "Found 3 relevant files", "duration_ms": 5200}),
        (-260, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "read", "label": "Reading existing RSS fetcher output format", "args": {"path": "rss_fetcher.py"}}),
        (-255, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "read", "label": "Read rss_fetcher.py (215 lines)", "duration_ms": 120}),
        (-250, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 5100, "label": "Designing summarizer with batch processing"}),
        (-240, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 2400, "label": "Generated content_summarizer.py implementation"}),
        (-235, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "write", "label": "Writing content_summarizer.py", "args": {"path": "content_summarizer.py"}}),
        (-230, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "write", "label": "Wrote content_summarizer.py (156 lines)", "duration_ms": 340}),
        (-225, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Running content_summarizer.py tests", "args": {"command": "python -m pytest test_summarizer.py -v"}}),
        (-210, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Tests: 2 passed, 1 failed", "duration_ms": 15400}),
        (-205, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 3800, "label": "Fixing failed test — batch size handling"}),
        (-195, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 900, "label": "Fix for batch processing edge case"}),
        (-190, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Patching content_summarizer.py batch logic", "args": {"path": "content_summarizer.py"}}),
        (-185, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Applied fix to content_summarizer.py", "duration_ms": 180}),
        (-180, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Re-running tests after fix", "args": {"command": "python -m pytest test_summarizer.py -v"}}),
        (-165, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Tests: 3 passed", "duration_ms": 14800}),
        (-160, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 4500, "label": "Adding error handling and retry logic"}),
        (-150, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 1600, "label": "Added retry with exponential backoff"}),
        (-145, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Adding retry decorator to API calls", "args": {"path": "content_summarizer.py"}}),
        (-140, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Applied retry logic to content_summarizer.py", "duration_ms": 210}),
        (-130, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 2900, "label": "Writing docstrings and type hints"}),
        (-120, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 1100, "label": "Added comprehensive docstrings"}),
        (-115, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Adding docstrings to content_summarizer.py", "args": {"path": "content_summarizer.py"}}),
        (-110, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Docstrings added to content_summarizer.py", "duration_ms": 190}),
        (-100, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "write", "label": "Writing test_content_summarizer.py", "args": {"path": "test_content_summarizer.py"}}),
        (-95, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "write", "label": "Wrote test_content_summarizer.py (89 lines)", "duration_ms": 280}),
        (-90, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Running full test suite", "args": {"command": "python -m pytest -v"}}),
        (-70, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "All 7 tests passed", "duration_ms": 19600}),
        (-65, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 3200, "label": "Reviewing implementation completeness"}),
        (-55, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 800, "label": "Implementation looks complete, adding config validation"}),
        (-50, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Adding config validation to content_summarizer.py", "args": {"path": "content_summarizer.py"}}),
        (-45, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "edit", "label": "Config validation added", "duration_ms": 160}),
        (-40, "tool_start", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "Final test run", "args": {"command": "python -m pytest -v"}}),
        (-25, "tool_end", {"agent_id": "jbcp-worker-1", "tool": "exec", "label": "All 8 tests passed", "duration_ms": 14200}),
        (-20, "llm_input", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 1500, "label": "Preparing completion summary"}),
        (-15, "llm_output", {"agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6", "tokens": 600, "label": "Content Summarizer implementation complete"}),
    ]

    for offset_sec, signal_type, extra in events:
        ts = (base + timedelta(seconds=offset_sec)).isoformat()
        signal = {
            "signal": signal_type,
            "timestamp": ts,
            "component_name": "Content Summarizer",
            "mission_id": MISSION_NEWS,
            **extra,
        }
        signals.append(signal)

    return signals


def get_next_mock_signal():
    """Return a single mock signal for the live SSE stream, cycling through
    realistic build activity for the Daily News Digest mission."""
    _cycle = [
        ("llm_input", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 3800, "label": "Analyzing summarizer output format",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("llm_output", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 1200, "text_preview": "I'll update the batch processing to handle...",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("tool_start", {
            "agent_id": "jbcp-worker-1", "tool": "edit", "source": "edit",
            "session_id": "mock-session-news-build",
            "label": "Editing content_summarizer.py",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "edit", "ok": True,
            "session_id": "mock-session-news-build",
            "result_preview": "Applied changes to batch processing logic",
            "result_chars": 342,
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("tool_start", {
            "agent_id": "jbcp-worker-1", "tool": "exec", "source": "bash",
            "session_id": "mock-session-news-build",
            "label": "Running pytest test_summarizer.py -v",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "exec", "ok": True,
            "session_id": "mock-session-news-build",
            "result_preview": "All 8 tests passed",
            "result_chars": 1847,
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("llm_input", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 4100, "label": "Planning Slack Poster component",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("llm_output", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 1900, "text_preview": "I'll create the Slack webhook poster with Block Kit...",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_start", {
            "agent_id": "jbcp-worker-1", "tool": "write", "source": "write",
            "session_id": "mock-session-news-build",
            "label": "Writing slack_poster.py",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "write", "ok": True,
            "session_id": "mock-session-news-build",
            "result_preview": "Created slack_poster.py (128 lines)",
            "result_chars": 4210,
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_start", {
            "agent_id": "jbcp-worker-1", "tool": "web_search", "source": "web_search",
            "session_id": "mock-session-news-build",
            "label": "Searching: Slack Block Kit message format",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "web_search", "ok": True,
            "session_id": "mock-session-news-build",
            "result_preview": "Found Slack Block Kit documentation",
            "result_chars": 2100,
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("agent_turn", {
            "agent_id": "jbcp-worker-1",
            "session_id": "mock-session-news-build",
            "status": "success",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("llm_input", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 2200, "label": "Reviewing Content Summarizer tests",
            "component_name": "Content Summarizer", "mission_id": MISSION_NEWS,
        }),
        ("tool_start", {
            "agent_id": "jbcp-worker-1", "tool": "edit", "source": "edit",
            "session_id": "mock-session-news-build",
            "label": "Editing slack_poster.py",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "edit", "ok": True,
            "session_id": "mock-session-news-build",
            "result_preview": "Added Block Kit formatting",
            "result_chars": 567,
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("tool_end", {
            "agent_id": "jbcp-worker-1", "tool": "exec", "ok": False,
            "session_id": "mock-session-news-build",
            "result_preview": "ImportError: No module named 'slack_sdk'",
            "result_chars": 203,
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
        ("llm_input", {
            "agent_id": "jbcp-worker-1", "model": "claude-sonnet-4-6",
            "session_id": "mock-session-news-build",
            "tokens": 1800, "label": "Fixing import error in Slack Poster",
            "component_name": "Slack Poster", "mission_id": MISSION_NEWS,
        }),
    ]

    if not hasattr(get_next_mock_signal, '_index'):
        get_next_mock_signal._index = 0

    idx = get_next_mock_signal._index % len(_cycle)
    get_next_mock_signal._index += 1

    signal_type, extra = _cycle[idx]
    return {
        "signal": signal_type,
        "timestamp": _now().isoformat(),
        **extra,
    }


def get_chat_history(workspace_id: str):
    """Return mock chat messages for a workspace."""
    if workspace_id == WS1_ID:
        return {
            "messages": [
                {"role": "user", "content": "I want to build a daily news digest that pulls from my favorite RSS feeds, summarizes the articles, and posts them to my team Slack.", "timestamp": _ago(minutes=185)},
                {"role": "assistant", "content": "Great idea! Let me break this down. We'll need:\n\n1. **RSS Fetcher** — pulls articles from your configured feeds\n2. **Content Summarizer** — uses Claude to create concise summaries\n3. **Slack Poster** — formats and posts the digest\n4. **Scheduler** — triggers the pipeline on your preferred schedule\n\nWhat RSS feeds do you want to include? And what time should the digest post?", "timestamp": _ago(minutes=184)},
                {"role": "user", "content": "TechCrunch, Hacker News top stories, and Ars Technica. Post at 8am Pacific every day.", "timestamp": _ago(minutes=183)},
                {"role": "assistant", "content": "Perfect. I'll set up:\n- TechCrunch RSS, HN front page, Ars Technica feeds\n- Summaries: 2-3 sentences per article, top 10 articles\n- Slack post at 8:00 AM PT daily\n\nI've generated the mission plan with 4 components and 6 tasks. The RSS Fetcher is complete and the Content Summarizer is currently being built. Want me to show the component graph?", "timestamp": _ago(minutes=182)},
                {"role": "user", "content": "Looks good, go ahead and build it!", "timestamp": _ago(minutes=181)},
                {"role": "assistant", "content": "Building now! The RSS Fetcher is done (215 lines, supports all 3 feeds with deduplication). The Content Summarizer is currently being implemented by the worker agent — it's writing the Claude API integration with batch processing support. Slack Poster and Scheduler will follow.", "timestamp": _ago(minutes=60)},
            ],
            "session_key": f"agent:main:jbcp-frontend:company:{WS1_ID}",
            "total": 5,
        }
    elif workspace_id == WS2_ID:
        return {
            "messages": [
                {"role": "user", "content": "Build me a BTC price alert. Check every minute and text me if it goes above 100k or below 90k.", "timestamp": _ago(minutes=2010)},
                {"role": "assistant", "content": "Done! I've set up a BTC price alert pipeline:\n\n- **CoinGecko Fetcher** — checks BTC/USD every minute\n- **Price Threshold** — alerts when price > $100k or < $90k (with 30-min cooldown)\n- **SMS Sender** — sends alerts to your phone via Twilio\n\nThe service is live and running. You've received 2 alerts in the last 24 hours.", "timestamp": _ago(minutes=1680)},
            ],
            "session_key": f"agent:main:jbcp-frontend:company:{WS2_ID}",
            "total": 2,
        }
    return {
        "messages": [],
        "session_key": f"agent:main:jbcp-frontend:company:{workspace_id}",
        "total": 0,
    }
