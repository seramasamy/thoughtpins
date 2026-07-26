import { Activity, Archive, BookOpen, CalendarRange, ClipboardList, FileText, Landmark, MapPin, Pin, Plus, Settings2, UsersRound } from "lucide-react";
import { ChatGlyph } from "../components/ui";
import type { NavItem, View } from "./types";

export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { view: "recap", label: "Recap", shortLabel: "Recap", icon: <CalendarRange size={20} strokeWidth={1.9} /> },
  { view: "people", label: "People", shortLabel: "People", icon: <UsersRound size={20} strokeWidth={1.9} /> },
  { view: "chat", label: "Chat", shortLabel: "Chat", icon: <ChatGlyph className="chat-nav-glyph" /> },
  { view: "places", label: "Places", shortLabel: "Places", icon: <MapPin size={20} strokeWidth={1.9} /> },
  { view: "pins", label: "Pins", shortLabel: "Pins", icon: <Pin size={20} strokeWidth={1.9} /> },
];

export const UTILITY_NAV_ITEMS: NavItem[] = [
  { view: "capture", label: "New journal entry", shortLabel: "New", icon: <Plus size={18} /> },
  { view: "library", label: "Source library", shortLabel: "Library", icon: <Archive size={18} /> },
  { view: "entries", label: "All entries", shortLabel: "Entries", icon: <FileText size={18} /> },
  { view: "memory", label: "All memory cards", shortLabel: "Memory", icon: <Landmark size={18} /> },
  { view: "jobs", label: "Processing activity", shortLabel: "Activity", icon: <ClipboardList size={18} /> },
  { view: "status", label: "System status", shortLabel: "Status", icon: <Activity size={18} /> },
  { view: "account", label: "Settings & account", shortLabel: "Settings", icon: <Settings2 size={18} /> },
  { view: "legal", label: "Privacy & support", shortLabel: "Privacy", icon: <BookOpen size={18} /> },
];

export const NAV_ITEMS = [...PRIMARY_NAV_ITEMS, ...UTILITY_NAV_ITEMS];

export function viewTitle(view: View): string {
  return {
    recap: "Recap",
    people: "People",
    chat: "Chat",
    places: "Places",
    pins: "Pins",
    memory: "Memory",
    capture: "Capture",
    library: "Library",
    entries: "Entries",
    jobs: "Activity",
    status: "Status",
    account: "Account",
    legal: "Legal",
  }[view];
}

export function viewSubtitle(view: View): string {
  return {
    recap: "Daily, weekly, and monthly patterns from your journal",
    people: "The people who shape your days",
    chat: "Talk naturally with the memory that grows with you",
    places: "Where your memories happened",
    pins: "Articles, books, documents, and ideas you chose to keep",
    memory: "People, places, projects, and concepts",
    capture: "Explicit journal entry flow",
    library: "Articles, books, documents, and saved readings",
    entries: "Journal timeline",
    jobs: "Background saves, imports, and retries",
    status: "Runtime health",
    account: "Preferences, devices, and data controls",
    legal: "Policy and store-readiness links",
  }[view];
}
