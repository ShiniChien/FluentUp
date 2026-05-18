from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.reading.rss_fetcher import fetch_article_list, RSS_TOPICS
from core.reading.content_gen import fetch_markdown, rewrite_content, generate_questions
from core.reading.ui.scoring import score_all
from core.reading.ui.state import reset_state
from core.shared import get_text_provider


def render_idle(secrets: dict, store) -> None:
    st.title("📖 IELTS Reading Practice")

    if err := st.session_state.pop("reading_error", None):
        st.error(err)

    topic = st.selectbox(
        "Chọn chủ đề",
        options=list(RSS_TOPICS.keys()),
        index=list(RSS_TOPICS.keys()).index(st.session_state["reading_topic"]),
    )
    st.session_state["reading_topic"] = topic

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Tìm bài báo", type="primary", use_container_width=True):
            st.session_state["reading_phase"] = "fetching_list"
            st.rerun()
    with col2:
        if st.button("📋 Lịch sử", use_container_width=True):
            _show_history(store)


@st.dialog("Lịch sử bài đã làm", width="large")
def _show_history(store) -> None:
    if store is None:
        st.info("MongoDB chưa được cấu hình.")
        return
    user = current_user()
    user_id = user["username"] if user else "anonymous"
    docs = run_async(store.list_reading_attempts(user_id))
    if not docs:
        st.info("Bạn chưa làm bài nào.")
        return
    for doc in docs:
        for attempt in doc["attempts"]:
            score = attempt["score"]
            st.markdown(
                f"**{doc['title']}**  \n"
                f"{doc.get('topic', doc.get('category', ''))} · "
                f"{attempt['attempted_at'].strftime('%Y-%m-%d') if hasattr(attempt['attempted_at'], 'strftime') else str(attempt['attempted_at'])[:10]}  \n"
                f"Score: {score['raw']}/{score['total']} · Band **{score['band']}**"
            )
            st.divider()


def render_fetching_list(secrets: dict) -> None:
    st.title("📖 IELTS Reading Practice")
    topic = st.session_state["reading_topic"]

    with st.status(f"Đang tải danh sách bài — {topic}...", expanded=True) as status:
        st.write(f"🔍 Lấy feed từ Google News ({topic})...")
        try:
            articles = run_async(fetch_article_list(topic))
        except ValueError as exc:
            status.update(label="Lỗi khi tải feed", state="error")
            st.session_state["reading_error"] = str(exc)
            st.session_state["reading_phase"] = "idle"
            st.rerun()
            return
        st.write(f"✅ Tìm được {len(articles)} bài")
        status.update(label=f"Đã tải {len(articles)} bài báo", state="complete")

    st.session_state["reading_articles_list"] = articles
    st.session_state["reading_phase"] = "article_list"
    st.rerun()


def render_article_list() -> None:
    st.title("📖 Chọn bài báo để luyện đọc")
    topic    = st.session_state["reading_topic"]
    articles = st.session_state["reading_articles_list"]

    st.caption(f"Chủ đề: **{topic}** — chọn 1 bài để bắt đầu")

    if st.button("← Quay lại", use_container_width=False):
        st.session_state["reading_phase"] = "idle"
        st.rerun()

    st.markdown("---")

    for i, art in enumerate(articles):
        col_title, col_btn = st.columns([5, 1])
        with col_title:
            date_str = art.pub_date[:16] if art.pub_date else ""
            st.markdown(f"**{i + 1}. {art.title}**  \n{date_str}")
        with col_btn:
            if st.button("Chọn", key=f"pick_{i}", use_container_width=True):
                st.session_state["reading_selected"] = {
                    "title":    art.title,
                    "link":     art.link,
                    "pub_date": art.pub_date,
                    "topic":    topic,
                }
                st.session_state["reading_phase"] = "fetching_content"
                st.rerun()


def render_fetching_content(secrets: dict, store) -> None:
    st.title("📖 IELTS Reading Practice")
    selected = st.session_state["reading_selected"]

    with st.status("Đang chuẩn bị bài đọc...", expanded=True) as status:

        # Check if already processed
        if store is not None:
            st.write("🗂️ Kiểm tra bài đã có trong database...")
            existing = run_async(store.get_reading_article_by_url(selected["link"]))
            if existing and existing.get("questions"):
                st.write("✅ Dùng lại bài đã xử lý")
                _load_from_existing(existing)
                status.update(label="Sẵn sàng!", state="complete")
                st.session_state["reading_phase"] = "reading"
                st.rerun()
                return

        # Step 1: save stub
        doc_id = None
        if store is not None:
            st.write("💾 Lưu thông tin bài báo...")
            try:
                doc_id = run_async(store.save_reading_stub(
                    topic=selected["topic"],
                    title=selected["title"],
                    link=selected["link"],
                    pub_date=selected["pub_date"],
                ))
                st.session_state["reading_doc_id"] = doc_id
            except Exception:
                pass

        # Step 2: fetch markdown via jina
        st.write("📥 Tải nội dung bài báo qua Jina...")
        try:
            markdown = run_async(fetch_markdown(selected["link"]))
        except Exception as exc:
            status.update(label="Lỗi khi tải nội dung", state="error")
            st.session_state["reading_error"] = f"Không thể tải nội dung: {exc}"
            st.session_state["reading_phase"] = "idle"
            st.rerun()
            return

        if store is not None and doc_id:
            try:
                run_async(store.update_reading_markdown(doc_id, markdown))
            except Exception:
                pass

        # Step 3: LLM rewrite
        st.write("✍️ AI đang biên tập lại bài đọc...")
        provider = get_text_provider(secrets)
        try:
            llm_content = run_async(rewrite_content(markdown, provider))
        except Exception as exc:
            status.update(label="Lỗi khi biên tập nội dung", state="error")
            st.session_state["reading_error"] = f"Không thể biên tập nội dung: {exc}"
            st.session_state["reading_phase"] = "idle"
            st.rerun()
            return

        if store is not None and doc_id:
            try:
                run_async(store.update_reading_llm_content(doc_id, llm_content))
            except Exception:
                pass

        # Step 4: LLM question generation
        st.write("🤖 AI đang tạo câu hỏi fill-in-the-blank...")
        try:
            q_data = run_async(generate_questions(llm_content, provider))
        except Exception as exc:
            status.update(label="Lỗi khi tạo câu hỏi", state="error")
            st.session_state["reading_error"] = f"Không thể tạo câu hỏi: {exc}"
            st.session_state["reading_phase"] = "idle"
            st.rerun()
            return

        if store is not None and doc_id:
            try:
                run_async(store.update_reading_questions(
                    doc_id=doc_id,
                    requirement=q_data["requirement"],
                    questions=q_data["questions"],
                    answers=[q["answer"] for q in q_data["questions"]],
                ))
            except Exception:
                pass

        st.session_state["reading_article"] = {
            "title":    selected["title"],
            "link":     selected["link"],
            "topic":    selected["topic"],
            "pub_date": selected["pub_date"],
            "body":     llm_content,
        }
        st.session_state["reading_questions"] = q_data
        status.update(label="Sẵn sàng!", state="complete")

    st.session_state["reading_phase"] = "reading"
    st.rerun()


def _load_from_existing(doc: dict) -> None:
    st.session_state["reading_doc_id"] = doc["_id"]
    st.session_state["reading_article"] = {
        "title":    doc["title"],
        "link":     doc.get("link", doc.get("url", "")),
        "topic":    doc.get("topic", ""),
        "pub_date": doc.get("pub_date", ""),
        "body":     doc.get("llm_content", doc.get("body", "")),
    }
    st.session_state["reading_questions"] = {
        "requirement": doc.get("requirement", "NO MORE THAN THREE WORDS"),
        "questions":   doc.get("questions", []),
    }


def render_reading() -> None:
    article   = st.session_state["reading_article"]
    q_data    = st.session_state["reading_questions"]
    answers: dict = st.session_state["reading_answers"]

    st.title(f"📖 {article['title']}")
    st.caption(f"{article.get('topic', '')} · {article.get('pub_date', '')[:16]}")

    col_article, col_questions = st.columns([1, 1])

    with col_article:
        st.markdown("### Bài đọc")
        with st.container(height=600):
            for i, para in enumerate(article["body"].split("\n\n")):
                para = para.strip()
                if para:
                    st.markdown(f"**{i + 1}.** {para}")

    with col_questions:
        st.markdown("### Câu hỏi")
        requirement = q_data.get("requirement", "NO MORE THAN THREE WORDS")
        st.caption(f"Điền vào chỗ trống — {requirement}")
        with st.form("reading_form"):
            for i, q in enumerate(q_data.get("questions", [])):
                key = f"fill_{i}"
                answers[key] = st.text_input(
                    f"{i + 1}. {q['sentence']}",
                    value=answers.get(key, ""),
                    key=f"inp_{key}",
                )
            submitted = st.form_submit_button("✔ Nộp bài", type="primary", use_container_width=True)

    if submitted:
        st.session_state["reading_answers"] = answers
        st.session_state["reading_phase"]   = "scoring"
        st.rerun()


def render_result(secrets: dict, store) -> None:
    article   = st.session_state["reading_article"]
    q_data    = st.session_state["reading_questions"]
    answers   = st.session_state["reading_answers"]
    score     = st.session_state["reading_score"]

    if score is None:
        score = score_all(q_data, answers)
        st.session_state["reading_score"] = score

        user    = current_user()
        user_id = user["username"] if user else "anonymous"
        doc_id  = st.session_state.get("reading_doc_id")
        if store is not None and doc_id:
            try:
                run_async(store.push_reading_attempt(
                    doc_id=doc_id, user_id=user_id,
                    answers=answers,
                    score={"raw": score["raw"], "total": score["total"], "band": score["band"]},
                ))
            except Exception:
                pass

    st.title(f"📖 Kết quả — {article['title']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Điểm", f"{score['raw']} / {score['total']}")
    col2.metric("Band", score["band"])
    col3.metric("Tỉ lệ đúng", f"{int(score['raw'] / (score['total'] or 1) * 100)}%")

    st.markdown("---")
    st.markdown("### Chi tiết")
    for i, r in enumerate(score.get("fill_blank", [])):
        q    = q_data["questions"][i]
        icon = "✅" if r["correct"] else "❌"
        st.markdown(f"{icon} **{i + 1}.** {q['sentence']}")
        if not r["correct"]:
            st.caption(f"Bạn trả lời: `{r['user']}` · Đúng: `{r['expected']}`")

    st.markdown("---")
    if st.button("▶ Làm bài mới", type="primary"):
        reset_state()
        st.rerun()
