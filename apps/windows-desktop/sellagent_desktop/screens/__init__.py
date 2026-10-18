"""Screen registry: (key, title, module, class). Order defines the sidebar."""

from __future__ import annotations

SCREEN_SPECS: list[tuple[str, str, str, str]] = [
    ("setup", "Setup", "setup_wizard", "SetupScreen"),
    ("models", "AI model manager", "model_manager", "ModelManagerScreen"),
    ("dashboard", "Dashboard", "dashboard", "DashboardScreen"),
    ("contacts", "CRM contacts", "contacts", "ContactsScreen"),
    ("contact_detail", "Contact detail", "contact_detail", "ContactDetailScreen"),
    ("import_export", "Import / export", "import_export", "ImportExportScreen"),
    ("campaigns", "Campaigns", "campaigns", "CampaignsScreen"),
    ("eligibility", "Eligibility & consent", "eligibility", "EligibilityScreen"),
    ("call_queue", "Call queue", "call_queue", "CallQueueScreen"),
    ("live_call", "Live call console", "live_call", "LiveCallScreen"),
    ("call_history", "Call history", "call_history", "CallHistoryScreen"),
    ("diagnostics", "AI & speech diagnostics", "diagnostics", "DiagnosticsScreen"),
    ("knowledge", "FITRON knowledge base", "knowledge", "KnowledgeScreen"),
    ("scripts", "Sales script editor", "script_editor", "ScriptEditorScreen"),
    ("followups", "Follow-ups", "followups", "FollowupsScreen"),
    ("analytics", "Analytics & reports", "analytics", "AnalyticsScreen"),
    ("devices", "Android device pairing", "devices", "DevicesScreen"),
    ("audio_tests", "Audio feasibility tests", "audio_tests", "AudioTestsScreen"),
    ("suppression", "Suppression & opt-out", "suppression", "SuppressionScreen"),
    ("settings", "Settings & privacy", "settings", "SettingsScreen"),
    ("backup", "Backup & restore", "backup", "BackupScreen"),
    ("logs", "Logs, health & version", "logs", "LogsScreen"),
]


def load_screen_class(module: str, cls: str):
    import importlib

    mod = importlib.import_module(f"sellagent_desktop.screens.{module}")
    return getattr(mod, cls)
