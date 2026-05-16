"""pages/0_Home.py — FluentUp landing page with login and user management."""
from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user, build_root_user, hash_password, is_logged_in, is_root, logout, verify_password
from core.shared import get_store, load_secrets, get_text_provider, set_text_provider_name
from core.text_provider import GEMINI_MODELS, GEMMA_MODELS, THINKING_LEVELS

# ── Shared CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
    .fu-card {
        border: 1.5px solid rgba(128,128,128,0.3); border-radius: 12px;
        padding: 28px 20px; text-align: center; height: 200px;
        display: flex; flex-direction: column; justify-content: center;
    }
    .fu-card .icon { font-size: 2.8em; }
    .fu-card h3  { margin: 8px 0 4px 0; }
    .fu-card p   { opacity: 0.6; font-size: 0.9em; margin: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

secrets = load_secrets()
store = get_store(secrets)

# ── Helper: profile fields form ───────────────────────────────────────────────
_OCC_LABELS = {"student": "Studying", "worker": "Working", "other": "Other"}
_OCC_DETAIL_PH = {
    "student": "e.g. Computer Science at HUST",
    "worker":  "e.g. Software engineer at a tech startup",
    "other":   "e.g. Recently graduated, preparing for IELTS",
}


def _user_profile_fields(prefix: str, defaults: dict) -> dict:
    name = st.text_input("Full name", value=defaults.get("name", ""), key=f"{prefix}_name")
    age = st.number_input(
        "Age", min_value=10, max_value=80,
        value=int(defaults.get("age") or 22), key=f"{prefix}_age",
    )
    occ_opts = list(_OCC_LABELS.keys())
    occ_idx = occ_opts.index(defaults.get("occupation", "student")) if defaults.get("occupation") in occ_opts else 0
    occupation = st.radio(
        "Currently…", options=occ_opts, format_func=lambda x: _OCC_LABELS[x],
        index=occ_idx, horizontal=True, key=f"{prefix}_occ",
    )
    detail = st.text_input(
        {"student": "What are you studying?", "worker": "What do you do?", "other": "Tell us more"}[occupation],
        value=defaults.get("occupation_detail", ""),
        placeholder=_OCC_DETAIL_PH[occupation],
        key=f"{prefix}_detail",
    )
    gender_opts = ["male", "female", "other"]
    gender_labels = {"male": "Male", "female": "Female", "other": "Other"}
    gen_idx = gender_opts.index(defaults.get("gender", "male")) if defaults.get("gender") in gender_opts else 0
    gender = st.radio(
        "Gender", options=gender_opts, format_func=lambda x: gender_labels[x],
        index=gen_idx, horizontal=True, key=f"{prefix}_gender",
    )
    return {"name": name, "age": int(age), "occupation": occupation,
            "occupation_detail": detail, "gender": gender}


# ── Login view ────────────────────────────────────────────────────────────────
def _render_login() -> None:
    st.markdown(
        "<div style='max-width:640px;margin:60px auto 0 auto;text-align:center'>"
        "<h1 style='font-size:3em;margin-bottom:4px'>🎯 FluentUp</h1>"
        "<p style='font-size:1.2em;opacity:0.65;margin-bottom:32px'>Luyện tiếng Anh thực chiến với AI</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("### Đăng nhập")
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập", key="login_username")
            password = st.text_input("Mật khẩu", type="password", key="login_password")
            submitted = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")
            else:
                # Check root first (always-on, not in DB)
                root = build_root_user(
                    secrets.get("ROOT_USERNAME", secrets.get("root_username", "root")),
                    secrets.get("ROOT_PASSWORD", secrets.get("root_password", "")),
                )
                if username.strip() == root["username"] and verify_password(password, root["password_hash"]):
                    st.session_state["current_user"] = root
                    st.rerun()
                elif store is None:
                    st.error("Không kết nối được MongoDB. Kiểm tra secrets.toml.")
                else:
                    try:
                        user_doc = run_async(store.get_user_by_username(username.strip()))
                    except Exception as e:
                        st.error(f"Lỗi kết nối: {e}")
                        st.stop()
                    if user_doc and verify_password(password, user_doc["password_hash"]):
                        st.session_state["current_user"] = user_doc
                        st.rerun()
                    else:
                        st.error("Tên đăng nhập hoặc mật khẩu không đúng.")


# ── Admin panel — Users section ───────────────────────────────────────────────
@st.dialog("Tạo tài khoản mới")
def _dialog_create_user() -> None:
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
                    st.session_state.pop("admin_users_cache", None)
                    st.rerun()


@st.dialog("Xác nhận xóa tài khoản")
def _dialog_confirm_delete(uid: str, username: str) -> None:
    st.warning(f"Bạn có chắc muốn xóa tài khoản **{username}** không? Hành động này không thể hoàn tác.")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Xóa", type="primary", use_container_width=True):
            try:
                run_async(store.delete_user(uid))
                st.session_state.pop("admin_users_cache", None)
                st.rerun()
            except Exception as e:
                st.error(f"Xóa thất bại: {e}")
    with col_cancel:
        if st.button("Hủy", use_container_width=True):
            st.rerun()


def _render_section_users() -> None:
    user = current_user()

    if st.button("➕ Tạo tài khoản mới", type="secondary"):
        _dialog_create_user()

    st.divider()
    st.markdown("#### Danh sách tài khoản")

    if "admin_users_cache" not in st.session_state:
        try:
            st.session_state["admin_users_cache"] = run_async(store.list_users()) if store else []
        except Exception as e:
            st.warning(f"Could not load user list: {e}")
            st.session_state["admin_users_cache"] = []

    users: list[dict] = st.session_state.get("admin_users_cache", [])

    if not users:
        st.caption("Không có tài khoản nào.")
        return

    for u in users:
        uid = str(u["_id"])
        is_self = uid == str(user.get("_id", ""))
        role_badge = "🔑" if u.get("role") == "root" else "👤"
        header = f"{role_badge} **{u['username']}**  —  {u.get('name', '')} {u.get('age') or ''}".rstrip(" —")

        col_h, col_edit, col_del = st.columns([6, 1, 1])
        with col_h:
            st.markdown(header)
        with col_edit:
            with st.popover("Sửa", use_container_width=True):
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
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi: {e}")
        with col_del:
            if not is_self:
                if st.button("Xóa", key=f"del_{uid}", use_container_width=True):
                    _dialog_confirm_delete(uid, u["username"])

        st.divider()


# ── Admin panel — Stats section ───────────────────────────────────────────────
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


# ── Admin panel — Scripts section ────────────────────────────────────────────
def _render_section_scripts() -> None:
    st.markdown("#### Scripts")

    # ── Migrate vocabulary ────────────────────────────────────────────────────
    st.markdown("**Migrate vocabulary: `notes` → `senses`**")
    st.caption(
        "Chuyển đổi các từ vựng còn lưu dạng cũ (`notes` string) sang schema mới (`senses` array). "
        "Script này idempotent — chạy lại sẽ không ảnh hưởng đến dữ liệu đã migrate."
    )

    if store is None:
        st.warning("Không có kết nối MongoDB.")
        return

    col_btn, col_status = st.columns([1, 4])
    with col_btn:
        run_clicked = st.button("▶ Chạy", key="btn_migrate_vocab", type="primary")

    if run_clicked:
        with st.spinner("Đang migrate..."):
            try:
                migrated = run_async(store.migrate_vocab())
            except Exception as e:
                st.error(f"Lỗi: {e}")
                migrated = None

        if migrated is not None:
            if migrated == 0:
                with col_status:
                    st.success("Không có document nào cần migrate (đã migrate hết rồi).")
            else:
                with col_status:
                    st.success(f"Đã migrate **{migrated}** document thành công.")


# ── Admin panel ───────────────────────────────────────────────────────────────
def _render_admin() -> None:
    user = current_user()

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

    tab_users, tab_provider, tab_stats, tab_scripts = st.tabs(["👤 Users", "🤖 AI Provider", "📊 Stats", "🔧 Scripts"])

    with tab_users:
        _render_section_users()
    with tab_provider:
        _render_section_provider()
    with tab_stats:
        _render_section_stats()
    with tab_scripts:
        _render_section_scripts()


# ── App cards (regular user) ──────────────────────────────────────────────────
def _render_app() -> None:
    user = current_user()
    name = user.get("name") or user.get("username", "")
    avatar_letter = name[0].upper() if name else "U"

    # Header bar
    col_logo, col_avatar = st.columns([6, 1])
    with col_logo:
        st.markdown(
            "<span style='font-size:1.4em;font-weight:700'>🎯 FluentUp</span>",
            unsafe_allow_html=True,
        )
    with col_avatar:
        with st.popover(
            f"**{avatar_letter}**",
            use_container_width=True,
        ):
            st.markdown(f"**{name}**")
            occ_label = {"student": "Đang học", "worker": "Đang đi làm", "other": "Khác"}.get(
                user.get("occupation", ""), ""
            )
            if user.get("occupation_detail"):
                st.caption(f"{occ_label} — {user['occupation_detail']}")
            elif occ_label:
                st.caption(occ_label)
            if user.get("age"):
                st.caption(f"Tuổi: {user['age']}")
            gender_label = {"male": "Nam", "female": "Nữ", "other": "Khác"}.get(
                user.get("gender", ""), ""
            )
            if gender_label:
                st.caption(f"Giới tính: {gender_label}")
            st.divider()
            if st.button("Đăng xuất", use_container_width=True, key="user_logout"):
                logout()
                st.rerun()

    st.divider()

    # ── Vocab review banner ───────────────────────────────────────────────────
    if store is not None and "_vocab_review_count" not in st.session_state:
        user_id = user.get("_id", "default")
        try:
            st.session_state["_vocab_review_count"] = run_async(
                store.count_review_vocab(user_id)
            )
        except Exception:
            st.session_state["_vocab_review_count"] = 0

    review_count: int = st.session_state.get("_vocab_review_count", 0)
    if review_count > 0:
        col_msg, col_btn = st.columns([5, 1])
        with col_msg:
            st.info(f"📚 Bạn có **{review_count}** từ vựng đang chờ review.")
        with col_btn:
            if st.button("Xem ngay →", use_container_width=True):
                st.session_state["_vocab_dialog_open"] = True
                st.rerun()

    st.divider()

    # ── Row 1: 5 skill cards ─────────────────────────────────────────────────
    st.markdown("### 🎓 Luyện kỹ năng IELTS")
    skill_cols = st.columns(5)
    _SKILLS = [
        ("🗣️", "Speaking",  "Luyện nói IELTS Part 1/2/3\nvới phản hồi AI thời gian thực.", "pages/1_Speaking.py"),
        ("🎧", "Listening", "Nghe hội thoại AI,\nđiền từ hoặc ghi chép.", "pages/2_Listening.py"),
        ("✍️", "Writing",   "Viết Task 1 & 2,\nnhận phản hồi chi tiết từ AI.", "pages/4_Writing.py"),
        ("📖", "Reading",   "Đọc báo thật,\ntrả lời câu hỏi IELTS style.", "pages/5_Reading.py"),
        ("💬", "Live Chat", "Trò chuyện audio\ntrực tiếp với AI companion.", "pages/3_Chat.py"),
    ]
    for col, (icon, title, desc, page) in zip(skill_cols, _SKILLS):
        with col:
            st.markdown(
                f'<div class="fu-card"><div class="icon">{icon}</div>'
                f'<h3>{title}</h3><p>{desc}</p></div>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            if st.button(f"Vào {title} →", type="primary", use_container_width=True, key=f"btn_{title}"):
                st.switch_page(page)

    st.markdown("")

    # ── Row 2: Practice section ──────────────────────────────────────────────
    st.markdown("### 🏋️ Practice")
    st.caption("Rèn luyện từng kỹ năng riêng lẻ, lặp đi lặp lại.")
    practice_cols = st.columns(3)
    _PRACTICE = [
        ("🎙️", "Dictation",       "Nghe câu AI đọc,\ngõ lại từng chữ.", "dictation"),
        ("🔁", "Shadowing",        "Nghe rồi nói lại — luyện\nphát âm và ngữ điệu.", "shadowing"),
        ("🃏", "Vocab Flashcards", "Ôn từ vựng của bạn\ntheo kiểu flashcard.", "flashcards"),
    ]
    for col, (icon, title, desc, mode) in zip(practice_cols, _PRACTICE):
        with col:
            st.markdown(
                f'<div class="fu-card"><div class="icon">{icon}</div>'
                f'<h3>{title}</h3><p>{desc}</p></div>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            if st.button("Bắt đầu →", type="secondary", use_container_width=True, key=f"btn_practice_{mode}"):
                st.session_state["practice_mode"] = mode
                st.switch_page("pages/6_Practice.py")


# ── Provider toggle (root only) ───────────────────────────────────────────────
def _render_section_provider() -> None:
    """Root-only: configure and save text-generation provider settings."""

    # ── Load current config (cached per session, cleared on save) ────────────
    if "admin_prov_cfg" not in st.session_state:
        cfg: dict = {}
        if store is not None:
            try:
                cfg = run_async(store.get_provider_config()) or {}
            except Exception:
                cfg = {}
        st.session_state["admin_prov_cfg"] = cfg

    cfg = st.session_state["admin_prov_cfg"]

    if "active_provider" not in cfg:
        cfg = {
            "active_provider": secrets.get("text_provider", "openrouter"),
            "providers": {
                "openrouter": {
                    "base_url": secrets.get("openrouter_base_url", ""),
                    "api_key":  secrets.get("openrouter_api_key", ""),
                    "model":    secrets.get("openrouter_model", ""),
                },
                "google": {
                    "model":           secrets.get("gemma_model", "gemma-4-31b-it"),
                    "thinking_budget": None,
                },
            },
        }

    active = cfg.get("active_provider", "openrouter")
    or_cfg = cfg.get("providers", {}).get("openrouter", {})
    g_cfg  = cfg.get("providers", {}).get("google", {})

    # ── Active provider radio ─────────────────────────────────────────────────
    st.markdown("#### Text Provider")
    chosen_active = st.radio(
        "Active provider",
        options=["openrouter", "google"],
        index=0 if active == "openrouter" else 1,
        horizontal=True,
        key="prov_active_radio",
    )

    st.markdown("---")

    # ── OpenRouter config ─────────────────────────────────────────────────────
    st.markdown("**OpenRouter**")
    or_base_url = st.text_input("Base URL", value=or_cfg.get("base_url", ""), key="prov_or_url")
    or_api_key  = st.text_input("API Key",  value=or_cfg.get("api_key", ""),  key="prov_or_key", type="password")
    or_model    = st.text_input("Model",    value=or_cfg.get("model", ""),    key="prov_or_model")

    st.markdown("---")

    # ── Google config ─────────────────────────────────────────────────────────
    st.markdown("**Google**")

    current_g_model = g_cfg.get("model", GEMMA_MODELS[0])
    is_gemini       = current_g_model in GEMINI_MODELS

    family = st.radio(
        "Model family",
        options=["Gemini", "Gemma"],
        index=0 if is_gemini else 1,
        horizontal=True,
        key="prov_g_family",
    )

    if family == "Gemini":
        model_list    = GEMINI_MODELS
        default_model = current_g_model if current_g_model in GEMINI_MODELS else GEMINI_MODELS[0]
    else:
        model_list    = GEMMA_MODELS
        default_model = current_g_model if current_g_model in GEMMA_MODELS else GEMMA_MODELS[0]

    g_model = st.selectbox(
        "Model", options=model_list, index=model_list.index(default_model), key="prov_g_model",
    )

    g_thinking_budget: int | None = None
    if family == "Gemini":
        level_names   = list(THINKING_LEVELS.keys())
        current_budget = g_cfg.get("thinking_budget", 0)
        reverse_map   = {v: k for k, v in THINKING_LEVELS.items()}
        current_level = reverse_map.get(current_budget, "Off")
        level_idx     = level_names.index(current_level) if current_level in level_names else 0
        chosen_level  = st.selectbox(
            "Thinking", options=level_names, index=level_idx, key="prov_g_thinking",
        )
        g_thinking_budget = THINKING_LEVELS[chosen_level]
    else:
        st.caption("Thinking always on — not configurable for Gemma models.")

    # ── Save ──────────────────────────────────────────────────────────────────
    st.markdown("")
    if st.button("💾 Save", type="primary"):
        new_providers = {
            "openrouter": {
                "base_url": or_base_url.strip(),
                "api_key":  or_api_key.strip(),
                "model":    or_model.strip(),
            },
            "google": {
                "model":           g_model,
                "thinking_budget": g_thinking_budget,
            },
        }

        if store is not None:
            try:
                run_async(store.save_provider_config(
                    active=chosen_active,
                    providers=new_providers,
                ))
                set_text_provider_name(chosen_active)
                st.session_state.pop("admin_prov_cfg", None)
                active_model = g_model if chosen_active == "google" else or_model
                st.success(f"Saved. Active: **{chosen_active}** / **{active_model}**")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
        else:
            st.warning("No MongoDB connection — settings not persisted (session only).")
            st.session_state["admin_prov_cfg"] = {
                "active_provider": chosen_active,
                "providers": new_providers,
            }
            set_text_provider_name(chosen_active)
            st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
if not is_logged_in():
    _render_login()
elif is_root():
    _render_admin()
else:
    _render_app()
