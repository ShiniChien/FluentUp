# Admin Panel Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `pages/0_Home.py` admin panel into a sidebar + content layout with Users, AI Provider, and Stats (disabled placeholder) sections.

**Architecture:** Two-column `st.columns([1.6, 5])` layout. Left column = nav sidebar (Streamlit buttons styled via CSS injection). Right column = content area rendering the active section. Nav state in `st.session_state["admin_section"]`.

**Tech Stack:** Streamlit, Python, CSS injection via `st.markdown(unsafe_allow_html=True)`

---

### Task 1: CSS injection + sidebar nav skeleton

**Files:**
- Modify: `pages/0_Home.py`

- [ ] **Step 1: Add CSS constants at top of `_render_admin()`**

Replace the current `_render_admin()` function header with this CSS block injected first:

```python
def _render_admin() -> None:
    user = current_user()

    st.markdown("""
    <style>
    /* Admin sidebar nav buttons — strip all Streamlit button chrome */
    [data-testid="stVerticalBlock"] .admin-nav-wrap button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #8b949e !important;
        text-align: left !important;
        padding: 6px 10px !important;
        border-radius: 6px !important;
        font-size: 0.9em !important;
        width: 100% !important;
    }
    [data-testid="stVerticalBlock"] .admin-nav-wrap button:hover {
        color: #c9d1d9 !important;
        background: rgba(255,255,255,0.05) !important;
    }
    .admin-nav-active button {
        background: rgba(31,111,235,0.15) !important;
        color: #58a6ff !important;
    }
    .admin-soon {
        display:inline-block;font-size:9px;background:#21262d;
        color:#6e7681;padding:1px 5px;border-radius:10px;
        margin-left:6px;vertical-align:middle;
    }
    </style>
    """, unsafe_allow_html=True)
```

- [ ] **Step 2: Add header row (title + logout)**

```python
    col_title, col_logout = st.columns([5, 1])
    with col_title:
        st.markdown(
            f"<span style='font-size:1.1em;font-weight:600'>🔑 {user['username']} — Admin Panel</span>",
            unsafe_allow_html=True,
        )
    with col_logout:
        if st.button("Đăng xuất", use_container_width=True, key="admin_logout"):
            logout()
            st.rerun()

    st.divider()
```

- [ ] **Step 3: Add two-column layout + nav state init**

```python
    if "admin_section" not in st.session_state:
        st.session_state["admin_section"] = "users"

    col_nav, col_content = st.columns([1.6, 5])
```

- [ ] **Step 4: Render nav in left column**

```python
    with col_nav:
        section = st.session_state["admin_section"]

        def _nav_btn(label: str, key: str) -> None:
            active_class = "admin-nav-active" if section == key else ""
            st.markdown(f'<div class="admin-nav-wrap {active_class}">', unsafe_allow_html=True)
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state["admin_section"] = key
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        _nav_btn("👤  Users", "users")
        _nav_btn("🤖  AI Provider", "provider")
        st.markdown(
            '<div style="color:#555;padding:6px 10px;font-size:0.9em;cursor:default">'
            '📊  Stats <span class="admin-soon">Soon</span></div>',
            unsafe_allow_html=True,
        )
```

- [ ] **Step 5: Stub content column**

```python
    with col_content:
        pass  # sections rendered in Tasks 2-4
```

- [ ] **Step 6: Syntax-check**

```bash
conda run -n tmchien python -m py_compile pages/0_Home.py
```

Expected: no output (clean)

- [ ] **Step 7: Commit**

```bash
git add pages/0_Home.py
git commit -m "feat: admin panel — sidebar nav skeleton + CSS"
```

---

### Task 2: Users section

**Files:**
- Modify: `pages/0_Home.py`

- [ ] **Step 1: Extract users content into `_render_section_users()`**

Move all content from the old `_render_admin()` between `st.divider()` (after create form) and `_render_provider_toggle()` call into a new function:

```python
def _render_section_users() -> None:
    """Create-user form + user list."""
    # Create user form
    with st.expander("➕ Tạo tài khoản mới", expanded=st.session_state.get("admin_create_open", False)):
        with st.form("create_user_form", clear_on_submit=True):
            st.markdown("#### Thông tin đăng nhập")
            new_username = st.text_input("Tên đăng nhập *", key="cu_username")
            c1, c2 = st.columns(2)
            with c1:
                new_pass = st.text_input("Mật khẩu *", type="password", key="cu_pass")
            with c2:
                new_pass2 = st.text_input("Xác nhận mật khẩu *", type="password", key="cu_pass2")
            st.markdown("#### Thông tin cá nhân")
            profile_fields = _user_profile_fields("cu", {})
            submitted = st.form_submit_button("Tạo tài khoản", type="primary")
            if submitted:
                if not new_username.strip():
                    st.error("Tên đăng nhập không được để trống.")
                elif not new_pass:
                    st.error("Mật khẩu không được để trống.")
                elif new_pass != new_pass2:
                    st.error("Mật khẩu xác nhận không khớp.")
                elif store is None:
                    st.error("Không có kết nối MongoDB.")
                else:
                    try:
                        uid = run_async(store.create_user(
                            username=new_username.strip(),
                            password_hash=hash_password(new_pass),
                            **profile_fields,
                        ))
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                        uid = None
                    if uid is None:
                        st.error(f"Tên đăng nhập '{new_username.strip()}' đã tồn tại.")
                    else:
                        st.success(f"Đã tạo tài khoản '{new_username.strip()}'.")
                        st.session_state["admin_create_open"] = False
                        st.session_state.pop("admin_users_cache", None)
                        st.rerun()

    st.divider()
    st.markdown("#### Danh sách tài khoản")

    if "admin_users_cache" not in st.session_state:
        try:
            st.session_state["admin_users_cache"] = run_async(store.list_users()) if store else []
        except Exception as e:
            st.warning(f"Could not load user list: {e}")
            st.session_state["admin_users_cache"] = []

    users: list[dict] = st.session_state.get("admin_users_cache", [])
    user = current_user()

    if not users:
        st.caption("Không có tài khoản nào.")
        return

    edit_id: str | None = st.session_state.get("admin_edit_id")

    for u in users:
        uid = u["_id"]
        is_self = uid == user.get("_id")
        role_badge = "🔑" if u.get("role") == "root" else "👤"
        header = f"{role_badge} **{u['username']}**  —  {u.get('name', '')} {u.get('age') or ''}".rstrip(" —")

        col_h, col_edit, col_del = st.columns([6, 1, 1])
        with col_h:
            st.markdown(header)
        with col_edit:
            if st.button("Sửa", key=f"edit_{uid}", use_container_width=True):
                st.session_state["admin_edit_id"] = uid if edit_id != uid else None
                st.rerun()
        with col_del:
            if not is_self:
                if st.button("Xóa", key=f"del_{uid}", use_container_width=True):
                    try:
                        run_async(store.delete_user(uid))
                        st.session_state.pop("admin_users_cache", None)
                        if edit_id == uid:
                            st.session_state.pop("admin_edit_id", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Xóa thất bại: {e}")

        if edit_id == uid:
            with st.form(f"edit_user_{uid}"):
                st.markdown("**Đổi mật khẩu** (để trống nếu không đổi)")
                ep1, ep2 = st.columns(2)
                with ep1:
                    e_pass = st.text_input("Mật khẩu mới", type="password", key=f"ep1_{uid}")
                with ep2:
                    e_pass2 = st.text_input("Xác nhận", type="password", key=f"ep2_{uid}")
                st.markdown("**Thông tin cá nhân**")
                defaults = {k: u.get(k, "") for k in
                            ("name", "age", "occupation", "occupation_detail", "gender")}
                e_profile = _user_profile_fields(f"eu_{uid}", defaults)
                if st.form_submit_button("Lưu thay đổi", type="primary"):
                    updates: dict = {**e_profile}
                    if e_pass:
                        if e_pass != e_pass2:
                            st.error("Mật khẩu xác nhận không khớp.")
                            st.stop()
                        updates["password_hash"] = hash_password(e_pass)
                    try:
                        run_async(store.update_user(uid, **updates))
                        st.success("Đã lưu.")
                        st.session_state.pop("admin_users_cache", None)
                        st.session_state.pop("admin_edit_id", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")

        st.divider()
```

- [ ] **Step 2: Call in content column**

In `_render_admin()`, inside `with col_content:`, replace `pass` with:

```python
    with col_content:
        section = st.session_state["admin_section"]
        if section == "users":
            _render_section_users()
        # provider + stats added in Tasks 3-4
```

- [ ] **Step 3: Delete old inline user management code from `_render_admin()`**

Remove everything between the old `st.divider()` and the `_render_provider_toggle()` call (now moved into `_render_section_users()`).

- [ ] **Step 4: Syntax-check**

```bash
conda run -n tmchien python -m py_compile pages/0_Home.py
```

Expected: no output

- [ ] **Step 5: Commit**

```bash
git add pages/0_Home.py
git commit -m "feat: admin panel — Users section extracted"
```

---

### Task 3: AI Provider section

**Files:**
- Modify: `pages/0_Home.py`

- [ ] **Step 1: Rename `_render_provider_toggle()` to `_render_section_provider()`**

```python
def _render_section_provider() -> None:
    """Root-only: switch the global text-generation provider."""
    st.markdown("#### Text Provider")

    current_name = st.session_state.get("text_provider", secrets.get("text_provider", "openrouter"))
    options = ["openrouter", "gemma"]
    idx = options.index(current_name) if current_name in options else 0

    chosen = st.radio(
        "Active provider",
        options=options,
        index=idx,
        horizontal=True,
        key="provider_radio",
    )

    if st.button("Save provider", type="primary"):
        set_text_provider(chosen, secrets)
        if store is not None:
            try:
                run_async(
                    store._client["fluentup"]["settings"].update_one(
                        {"_id": "config"},
                        {"$set": {"text_provider": chosen}},
                        upsert=True,
                    )
                )
                st.success(f"Provider set to **{chosen}** and saved to MongoDB.")
            except Exception as e:
                st.warning(f"Provider set in session but MongoDB save failed: {e}")
        else:
            st.info(f"Provider set to **{chosen}** (session only — no MongoDB).")
        st.rerun()
```

- [ ] **Step 2: Wire into content column**

```python
        if section == "users":
            _render_section_users()
        elif section == "provider":
            _render_section_provider()
```

- [ ] **Step 3: Remove the old `_render_provider_toggle()` call** from the end of the old `_render_admin()` (already cleaned up in Task 2 if done in order; verify it's gone).

- [ ] **Step 4: Syntax-check**

```bash
conda run -n tmchien python -m py_compile pages/0_Home.py
```

- [ ] **Step 5: Commit**

```bash
git add pages/0_Home.py
git commit -m "feat: admin panel — AI Provider section"
```

---

### Task 4: Stats placeholder section + smoke test

**Files:**
- Modify: `pages/0_Home.py`

- [ ] **Step 1: Add `_render_section_stats()`**

```python
def _render_section_stats() -> None:
    st.markdown("#### Usage Stats")
    st.markdown(
        "<div style='text-align:center;padding:48px 0;color:#8b949e'>"
        "<div style='font-size:2.5em;margin-bottom:12px'>📊</div>"
        "<div style='font-size:1.1em;margin-bottom:8px;color:#c9d1d9'>Usage Stats</div>"
        "<div>Tính năng đang phát triển.</div>"
        "<div style='margin-top:4px'>Thống kê phiên luyện tập và số user hoạt động sẽ có ở đây.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
```

- [ ] **Step 2: Wire into content column**

```python
        if section == "users":
            _render_section_users()
        elif section == "provider":
            _render_section_provider()
        elif section == "stats":
            _render_section_stats()
```

Note: Stats is not reachable via nav click (sidebar renders it as non-button), but the branch exists for completeness.

- [ ] **Step 3: Syntax-check**

```bash
conda run -n tmchien python -m py_compile pages/0_Home.py
```

- [ ] **Step 4: Import sanity check**

```bash
conda run -n tmchien python -c "import app"
```

Expected: no output

- [ ] **Step 5: Smoke test**

```bash
conda run -n tmchien streamlit run app.py --server.headless true &
sleep 6 && curl -s http://localhost:8501/_stcore/health
```

Expected: `"ok"`

- [ ] **Step 6: Final commit**

```bash
git add pages/0_Home.py
git commit -m "feat: admin panel — Stats placeholder + complete sidebar layout"
```
