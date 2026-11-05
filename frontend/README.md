# WorkspaceAI frontend

React + TypeScript application for the WorkspaceAI academic research workspace. It shares this directory with the existing Streamlit application (`app.py`, `state.py`, `styles.py`, and `components/`). Run the React interface with the commands below; the Streamlit application keeps its existing entry point.

## Run locally

Use Node.js 22 or newer and pnpm.

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open the address printed by Vite. To choose the development port explicitly:

```sh
pnpm dev --port 5174
```

## Build

```sh
pnpm build
pnpm preview
```

The build checks TypeScript and writes the production application to `dist/`. `pnpm format` formats frontend source files. The dependency lockfile and workspace build permissions are included for reproducible installs.

## Features

- Home hub with workspace creation, conversation history, search, feature filters, rename and delete actions.
- Separate workspace records for files, conversations, task suggestions, confirmed tasks and email drafts.
- Chat with right-aligned user messages, centered answers and composer, document citations, saved answers, loading, insufficient-evidence and retry states.
- Compact source picker with file-type filtering, search, ready-file bulk selection, expandable details and independently collapsible source/conversation panels.
- Task board with To-do, In progress, In Review, Design Review, Rework, Done, Not Started, Blocked, On Hold and Archived statuses. Suggestions require confirmation before becoming tasks.
- Email drafting with recipients, source evidence, reviewed payload snapshots, approval invalidation after edits and simulated send/retry outcomes.
- Sign-in, create-account and password-reset screens with Google, Microsoft, Apple and email/password controls, inline validation, password visibility and explicit availability feedback.
- Light/dark/system themes, responsive phone/tablet layouts and an interactive 390px phone preview. Routes, workspace data and theme changes synchronize between the phone preview and the main view.

## Prototype boundaries

This React application currently uses local demo data and browser storage. It is ready for UI review and backend integration.

- Chat responses, mode detection, task suggestions and email generation are deterministic frontend simulations.
- Uploaded files are marked **Preview only** and remain unavailable as evidence until extraction is connected.
- Email approval and delivery states demonstrate the workflow; real approval enforcement, authorization, SMTP and delivery confirmation belong to the backend.
- Sign-in controls currently explain that authentication is unavailable. They do not create accounts or sessions, send password-reset emails, or persist entered passwords. The remember-me checkbox is a preview control.
- The explicit demo action returns to the previous workspace without claiming authentication. Opening sign-in preserves the active conversation and its unsent chat input.
- Example document passages, dates, people and `example.edu` recipients in `src/data.ts` are fixtures for the demo.
- The 20-file limit is advisory; actual file/page validation requires backend integration.

## Routes and local state

| Route | Screen |
| --- | --- |
| `#home` | Workspace hub and conversation history |
| `#workspace/{workspaceId}/chat/{threadId}` | Exact chat conversation |
| `#workspace/{workspaceId}/tasks/{threadId}` | Workspace tasks and suggestions |
| `#workspace/{workspaceId}/email/{threadId}` | Per-thread email draft |
| `#login` | Sign-in preview |
| `#signup` | Account-creation preview |
| `#forgot-password` | Password-reset preview |

Workspace records use `workspaceai-v2` in local storage. Theme uses `wai-theme`; panel preferences use `wai-navigation-collapsed` and `wai-sources-collapsed`. Simulated delivery records use the `wai-delivery-*` keys. Session storage holds only the internal auth return route under `wai-auth-return`.

Archived tasks remain available through the status filter and are excluded from open-task counts. Source selection is scoped to each workspace, and each answer records the files selected when it was generated.

## Source map

| File | Responsibility |
| --- | --- |
| `src/App.tsx` | Routing, workspace updates, auth return navigation, history, evidence drawer and handoff |
| `src/Home.tsx` | Workspace cards and grouped conversation history |
| `src/Chat.tsx` | Composer, answers, citations, provisional results and recovery states |
| `src/Sources.tsx` | Search, filtering, source selection, metadata and upload preview |
| `src/Tasks.tsx` | Suggestion review, task editing, filters and board |
| `src/task-status.tsx` | Typed status catalog, colors, icons and lane grouping |
| `src/Email.tsx` | Draft editing, approval snapshots and mock delivery workflow |
| `src/Auth.tsx` | Sign-in, signup and reset preview forms |
| `src/DevicePreview.tsx` | Same-origin interactive phone viewport |
| `src/components.tsx` | Brand, theme, citations, notices and accessible dialogs/drawers |
| `src/data.ts` | Types, seed workspaces, source fixtures and mock routing |
| `src/styles.css` | Shared layout, tokens, typography and components |
| `src/interface.css` | Workspace identity colors, task tags and themed controls |
| `src/workspace-panels.css` | Collapsible navigation and source panels |
| `src/auth.css` | Auth forms and responsive account entry |

## Design

The interface follows the supplied orange/black/white identity and minimalism direction. Be Vietnam Pro 400/500/600 is bundled locally, including Vietnamese glyphs. Gradients are restricted to Home's brand surface; working views use flat surfaces, readable text and restrained status colors.

## Verification

TypeScript and production builds passed. Browser validation during development covered 76 authentication checks, 69 core interaction checks, 45 source/panel checks, 30 chat-layout checks, and 56 task-status/phone-preview checks. The suites were run as their respective features were completed; the auth and core suites were rerun before preparing this frontend snapshot.

Checks included workspace isolation, exact source locators, task confirmation, payload-bound approval, error recovery, password handling, retained unsent drafts, native-picker keyboard behavior and responsive layouts down to 320px. Source and app screen inspections in both themes reported no failures. Browser-review scripts and screenshots under `.taste-skill/` are machine-local development artifacts and are excluded from this repository.

## Connecting authentication

Connect the preview handlers in `src/Auth.tsx` to a server-backed identity service and provider configuration, then enforce sessions and workspace ownership on the backend. Useful provider references:

- [Google Identity](https://developers.google.com/identity/openid-connect/openid-connect)
- [Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/app-sign-in-flow)
- [Sign in with Apple for the web](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web/)

Provider marks are inline vectors; the Apple mark uses the [Simple Icons source](https://github.com/simple-icons/simple-icons/blob/develop/icons/apple.svg).
