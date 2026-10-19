"""Screen registry and sidebar navigation groups.

``SCREEN_SPECS`` lists every screen (key, title, module, class). ``NAV_GROUPS`` arranges them into the eleven sidebar
entries of the approved mockup; a group with several screens shows them as tabs. ``navigate(key)`` always works for
every screen key, so all screens stay reachable.
"""

from __future__ import annotations

SCREEN_SPECS: list[tuple[str, str, str, str]] = [
    ("setup", "Setup wizard", "setup_wizard", "SetupScreen"),
    ("models", "AI model manager", "model_manager", "ModelManagerScreen"),
    ("dashboard", "Dashboard", "dashboard", "DashboardScreen"),
    ("contacts", "Contacts", "contacts", "ContactsScreen"),
    ("contact_detail", "Contact detail", "contact_detail", "ContactDetailScreen"),
    ("import_export", "Import / export", "import_export", "ImportExportScreen"),
    ("campaigns", "Campaigns", "campaigns", "CampaignsScreen"),
    ("eligibility", "Eligibility & consent", "eligibility", "EligibilityScreen"),
    ("call_queue", "Call queue", "call_queue", "CallQueueScreen"),
    ("live_call", "Live call", "live_call", "LiveCallScreen"),
    ("call_history", "Call history", "call_history", "CallHistoryScreen"),
    ("diagnostics", "Speech & AI diagnostics", "diagnostics", "DiagnosticsScreen"),
    ("knowledge", "Knowledge Base", "knowledge", "KnowledgeScreen"),
    ("scripts", "Sales script editor", "script_editor", "ScriptEditorScreen"),
    ("persona", "AI sales persona", "persona", "PersonaScreen"),
    ("followups", "Follow-ups", "followups", "FollowupsScreen"),
    ("analytics", "Reports", "analytics", "AnalyticsScreen"),
    ("devices", "Pairing", "devices", "DevicesScreen"),
    ("provider", "Telephony provider", "provider", "ProviderScreen"),
    ("audio_tests", "Audio feasibility console", "audio_tests", "AudioTestsScreen"),
    ("suppression", "Suppression & opt-out", "suppression", "SuppressionScreen"),
    ("settings", "Privacy & calling settings", "settings", "SettingsScreen"),
    ("backup", "Backup & restore", "backup", "BackupScreen"),
    ("logs", "Health, logs & audit", "logs", "LogsScreen"),
    ("profile", "Profile", "profile", "ProfileScreen"),
    ("users", "Users & Roles", "users", "UsersScreen"),
    ("workers", "Workers", "workers", "WorkersScreen"),
]

# backend permission area per screen (GET needs '<area>:read', changes need '<area>:write')
SCREEN_AREAS: dict[str, str] = {
    "setup": "settings", "models": "ai", "dashboard": "reports", "contacts": "contacts", "contact_detail": "contacts", "import_export": "contacts",
    "campaigns": "campaigns", "eligibility": "contacts", "call_queue": "calls", "live_call": "calls", "call_history": "calls", "diagnostics": "ai", "persona": "settings",
    "knowledge": "knowledge", "scripts": "knowledge", "followups": "followups", "analytics": "reports", "devices": "devices", "provider": "settings", "audio_tests": "audio_tests",
    "suppression": "suppression", "settings": "settings", "backup": "backup", "logs": "health", "profile": "settings", "users": "users", "workers": "system",
}

# (nav key, sidebar label, [screen keys in tab order])
NAV_GROUPS: list[tuple[str, str, list[str]]] = [
    ("dashboard", "Dashboard", ["dashboard"]),
    ("contacts", "Contacts", ["contacts", "contact_detail", "eligibility"]),
    ("campaigns", "Campaigns", ["campaigns"]),
    ("console", "Call Console", ["live_call", "call_queue", "call_history"]),
    ("followups", "Follow-ups", ["followups"]),
    ("reports", "Reports", ["analytics"]),
    ("knowledge", "Knowledge Base", ["knowledge"]),
    ("ai", "AI Settings", ["models", "persona", "diagnostics", "scripts"]),
    ("devices", "Devices", ["devices", "audio_tests", "provider"]),
    ("system", "System Status", ["logs", "workers", "backup"]),
    ("settings", "Settings", ["settings", "users", "suppression", "import_export", "setup", "profile"]),
]


def group_for(screen_key: str) -> str:
    for nav_key, _label, keys in NAV_GROUPS:
        if screen_key in keys:
            return nav_key
    raise KeyError(screen_key)


def load_screen_class(module: str, cls: str):
    import importlib

    mod = importlib.import_module(f"sellagent_desktop.screens.{module}")
    return getattr(mod, cls)
