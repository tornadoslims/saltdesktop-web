# webui-v2/style.css

**Path:** `webui-v2/style.css` (1,890 lines)
**Purpose:** Complete CSS for the Salt Desktop web UI. Dark theme with cyan accent color.

## Design System

- **Theme:** Dark background (#0a0a0f), light text (#e8e8ec), cyan accent (#06b6d4)
- **Color palette:** success green (#22c55e), warning yellow (#eab308), error red (#ef4444)
- **Typography:** system font stack, 14px base size
- **Border radius:** 10px for cards, 6px for inputs
- **Spacing:** 8px base unit

## Layout Sections

- **`.sidebar`**: Fixed 240px left panel, dark background, scrollable
- **`.main-content`**: Flexible main area with padding
- **`.status-bar`**: Fixed bottom bar with ticker animation

## Key Component Styles

- **`.nav-item`**: Sidebar navigation links with hover/active states
- **`.company-section`**: Collapsible workspace sections with expand/collapse animation
- **`.sidebar-entry`**: Mission entries with phase dot indicators (green/yellow/gray)
- **`.card`**: Rounded dark surface cards
- **`.agent-row`**: Horizontal agent/service row with dot, info, badge
- **`.progress-bar`**: Horizontal progress bar with colored fill
- **`.mission-view`**: Full-height mission layout
- **`.mission-split`**: 50/50 chat/graph split for planning mode
- **`.chat-messages`**: Scrollable chat container with user/assistant message bubbles
- **`.graph-container`**: Canvas container for component graph
- **`.lifecycle-bar`**: Horizontal lifecycle stage indicator (PLANNING -> SPEC'D -> BUILDING -> LIVE)
- **`.component-card`**: Library component cards
- **`.connector-card`**: External service connector cards
- **`.modal-overlay`**: Centered modal dialogs
- **`.toggle-switch`**: iOS-style toggle for settings
- **`.ticker-track`**: Scrolling bottom ticker animation
