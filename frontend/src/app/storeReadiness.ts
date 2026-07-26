export type StoreGateStatus = "ready" | "needs-work" | "external";

export type StoreGate = {
  title: string;
  status: StoreGateStatus;
  reason: string;
  next: string;
};

export type StoreTool = {
  name: string;
  href: string;
  purpose: string;
  whenToUse: string;
};

export const STORE_GATES: StoreGate[] = [
  {
    title: "Not a thin web wrapper",
    status: "external",
    reason: "The web product loop and source-level native shells exist; final store proof still needs signed native builds and device screenshots.",
    next: "Run native device/simulator smokes and capture phone/tablet screenshots before App Store or Play Store submission.",
  },
  {
    title: "Account deletion and export",
    status: "ready",
    reason: "Backend and web app expose export, entry deletion, logout, and account deletion controls.",
    next: "Verify the same controls inside native builds before TestFlight or Play internal testing.",
  },
  {
    title: "Privacy and AI disclosure",
    status: "external",
    reason: "Reviewed privacy, terms, support, account deletion, and AI disclosure pages are packaged and served by the app/API image.",
    next: "Publish the same pages over HTTPS at thoughtpins.com and keep store-console metadata synchronized.",
  },
  {
    title: "Sign in with Apple parity",
    status: "external",
    reason: "If Google or another third-party sign-in is offered on iOS, Apple sign-in must be ready too.",
    next: "Enable Apple OAuth before iOS public review if any third-party OAuth is enabled.",
  },
  {
    title: "Review account and live backend",
    status: "external",
    reason: "Store reviewers need working credentials and a stable review environment.",
    next: "Create a staging review user, seed safe demo memories, and include review notes.",
  },
  {
    title: "Data safety inventory",
    status: "ready",
    reason: "A machine-readable inventory exists for account data, user content, identifiers, diagnostics, AI processing, deletion, and permissions.",
    next: "Copy the inventory into App Store Connect and Play Console, then keep it synchronized with production config.",
  },
];

export const STORE_TOOLS: StoreTool[] = [
  {
    name: "Playwright",
    href: "https://github.com/microsoft/playwright",
    purpose: "Cross-browser and responsive smoke tests for the web app contract.",
    whenToUse: "Add before staging so desktop, tablet, and mobile layouts are checked automatically.",
  },
  {
    name: "axe-core",
    href: "https://github.com/dequelabs/axe-core",
    purpose: "Accessibility checks for headings, labels, contrast, and keyboard navigation.",
    whenToUse: "Add with Playwright before native UI work so review-facing flows are accessible.",
  },
  {
    name: "Capacitor",
    href: "https://github.com/ionic-team/capacitor",
    purpose: "Optional native shell around web technology with access to device APIs.",
    whenToUse: "Use only if the app has native-grade behavior; do not submit a thin webview wrapper.",
  },
  {
    name: "fastlane",
    href: "https://github.com/fastlane/fastlane",
    purpose: "Automates screenshots, signing, TestFlight, Play internal testing, and store metadata delivery.",
    whenToUse: "Add after bundle IDs, signing, and native projects exist.",
  },
];
