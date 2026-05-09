# Admin Panel Redesign — Design Spec

**Date:** 2026-05-09

## Goal

Refactor the root admin panel from a single long-scroll page into a sidebar + content layout, making it polished and easy to extend with new sections later.

## Layout

Two-column layout using `st.columns([1.6, 5])`:

- **Left column** — sidebar navigation (fixed-width feel, ~160px equivalent)
- **Right column** — content area for the active section

The sidebar is minimal/borderless: background is one shade darker than the main app (`#0a0a0a` via CSS injection), no explicit border or card box. Active nav item gets a subtle accent highlight (`rgba(31, 111, 235, 0.15)` background + `#58a6ff` text). Inactive items are `#8b949e`. Logout link at the bottom in `#f85149`.

## Sidebar Sections

| Section | Icon | Status |
|---------|------|--------|
| Users | 👤 | Implemented |
| AI Provider | 🤖 | Implemented |
| Usage Stats | 📊 | Disabled — "Soon" badge |

Stats item: greyed out (`opacity: 0.4`), `cursor: default`, non-clickable, with a small "Soon" pill badge. Clicking it does nothing.

Nav state: `st.session_state["admin_section"]` — string, default `"users"`.

## Sections

### Users

Existing logic from `_render_admin()` — create user form (expander) + user list with edit/delete. No behavior changes.

### AI Provider

Existing logic from `_render_provider_toggle()`. Moved into the content area of the new layout (no longer appended below user list).

### Usage Stats (placeholder)

Simple centered placeholder:
```
📊
Usage Stats
Tính năng đang phát triển
Thống kê phiên luyện tập và số user hoạt động sẽ có ở đây.
```

## Header

Top of the page (above columns): one row with app title left and logout button right — replaces the current per-section logout buttons.

```
🔑 root — Admin Panel          [Đăng xuất]
```

## File Changes

**Modify only:** `pages/0_Home.py`

- Remove `_render_admin()` and `_render_provider_toggle()` as separate functions
- Add `_render_admin()` with the new two-column layout
- Add `_render_nav()` helper that renders the sidebar nav
- Add `_render_section_users()`, `_render_section_provider()`, `_render_section_stats()` for each content panel

No new files. The redesign is self-contained in `pages/0_Home.py`.

## CSS

Injected via `st.markdown(..., unsafe_allow_html=True)` at the top of `_render_admin()`:

```css
.admin-nav-item { ... }          /* base nav item */
.admin-nav-item.active { ... }   /* active highlight */
.admin-nav-item.disabled { ... } /* greyed out, no-click */
.admin-soon-badge { ... }        /* "Soon" pill */
```

Nav items are rendered as `st.markdown(html, unsafe_allow_html=True)` + `st.button` with `use_container_width=True` and custom CSS to hide button chrome. Alternatively, use pure HTML buttons with `onclick` not applicable in Streamlit — so use `st.button` with `label` styled via CSS.

**Pragmatic approach**: use `st.button` for clickable items (Users, AI Provider), style them with CSS to look like nav items. Stats uses `st.markdown` only (no button). Active state determined by `session_state["admin_section"]`.

## Out of Scope

- Actual Usage Stats implementation
- Any other new sections
- Mobile/responsive layout
- Persistent section state across page reloads
