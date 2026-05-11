from __future__ import annotations

import streamlit as st

from core.async_utils import run_async
from core.auth import current_user
from core.reading.rss_fetcher import fetch_article, RSS_FEEDS
from core.reading.question_gen import generate_questions
from core.reading.ui.scoring import score_all
from core.reading.ui.state import reset_state
from core.shared import get_text_provider


def render_idle(secrets: dict, store) -> None:
    st.title("📖 IELTS Reading Practice")

    if err := st.session_state.pop("reading_error", None):
        st.error(err)

    category = st.selectbox(
        "Chọn chủ đề",
        options=list(RSS_FEEDS.keys()),
        index=list(RSS_FEEDS.keys()).index(st.session_state["reading_category"]),
    )
    st.session_state["reading_category"] = category

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Bắt đầu bài mới", type="primary", use_container_width=True):
            st.session_state["reading_phase"] = "generating"
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
                f"{doc['category']} · {attempt['attempted_at'].strftime('%Y-%m-%d') if hasattr(attempt['attempted_at'], 'strftime') else attempt['attempted_at'][:10]}  \n"
                f"Score: {score['raw']}/{score['total']} · Band **{score['band']}**"
            )
            st.divider()


def render_generating(secrets: dict, store) -> None:
    st.title("📖 IELTS Reading Practice")
    category = st.session_state["reading_category"]

    with st.spinner("Đang tìm bài và tạo câu hỏi..."):
        try:
            article = fetch_article(category)
        except ValueError as exc:
            st.session_state["reading_error"] = str(exc)
            st.session_state["reading_phase"] = "idle"
            st.rerun()
            return

        # Dedup: reuse existing questions if article already in DB
        existing = None
        if store is not None:
            existing = run_async(store.get_reading_article_by_url(article.url))

        if existing:
            st.session_state["reading_article"]   = {
                "title": existing["title"], "body": existing["body"],
                "url": existing["url"], "category": existing["category"],
                "published_at": existing["published_at"],
            }
            st.session_state["reading_questions"] = existing["questions"]
            st.session_state["reading_doc_id"]    = existing["_id"]
        else:
            try:
                provider  = get_text_provider(secrets)
                questions = run_async(generate_questions(article, provider))
            except Exception as exc:
                st.session_state["reading_error"] = f"Không thể tạo câu hỏi: {exc}"
                st.session_state["reading_phase"] = "idle"
                st.rerun()
                return

            doc_id = None
            if store is not None:
                try:
                    doc_id = run_async(store.save_reading_article(
                        url=article.url, title=article.title, body=article.body,
                        category=article.category, published_at=article.published_at,
                        questions=questions,
                    ))
                except Exception:
                    pass

            st.session_state["reading_article"]   = {
                "title": article.title, "body": article.body,
                "url": article.url, "category": article.category,
                "published_at": article.published_at,
            }
            st.session_state["reading_questions"] = questions
            st.session_state["reading_doc_id"]    = doc_id

    st.session_state["reading_answers"] = {}
    st.session_state["reading_phase"]   = "reading"
    st.rerun()


def render_reading() -> None:
    article   = st.session_state["reading_article"]
    questions = st.session_state["reading_questions"]
    answers: dict = st.session_state["reading_answers"]

    st.title(f"📖 {article['title']}")
    st.caption(f"{article['category']} · {article.get('published_at', '')[:16]}")

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
        with st.form("reading_form"):
            _render_tfng(questions.get("tfng", []), answers)
            _render_headings(questions.get("headings", []), answers)
            _render_fill_blank(questions.get("fill_blank", []), answers)
            _render_mcq(questions.get("mcq", []), answers)

            submitted = st.form_submit_button("✔ Nộp bài", type="primary", use_container_width=True)

    if submitted:
        st.session_state["reading_answers"] = answers
        st.session_state["reading_phase"]   = "scoring"
        st.rerun()


def _render_tfng(questions: list[dict], answers: dict) -> None:
    if not questions:
        return
    with st.expander("Part 1 — True / False / Not Given", expanded=True):
        st.caption("Do the following statements agree with the information in the article?")
        for i, q in enumerate(questions):
            key = f"tfng_{i}"
            answers[key] = st.radio(
                f"{i + 1}. {q['statement']}",
                options=["True", "False", "Not Given"],
                index=["True", "False", "Not Given"].index(answers.get(key, "Not Given")),
                key=f"radio_{key}",
                horizontal=True,
            )


def _render_headings(questions: list[dict], answers: dict) -> None:
    if not questions:
        return
    with st.expander("Part 2 — Matching Headings", expanded=True):
        st.caption("Choose the most suitable heading for each paragraph.")
        for i, q in enumerate(questions):
            key = f"headings_{i}"
            opts = q["options"]
            prev = answers.get(key, opts[0])
            idx  = opts.index(prev) if prev in opts else 0
            answers[key] = st.selectbox(
                f"Paragraph {q['paragraph_idx'] + 1}",
                options=opts,
                index=idx,
                key=f"sel_{key}",
            )


def _render_fill_blank(questions: list[dict], answers: dict) -> None:
    if not questions:
        return
    with st.expander("Part 3 — Fill in the Blank", expanded=True):
        st.caption("Complete each sentence using NO MORE THAN the specified number of words from the article.")
        for i, q in enumerate(questions):
            key = f"fill_blank_{i}"
            answers[key] = st.text_input(
                f"{i + 1}. {q['sentence']}  ({q['word_limit']})",
                value=answers.get(key, ""),
                key=f"inp_{key}",
            )


def _render_mcq(questions: list[dict], answers: dict) -> None:
    if not questions:
        return
    with st.expander("Part 4 — Multiple Choice", expanded=True):
        for i, q in enumerate(questions):
            key  = f"mcq_{i}"
            opts = list(q["options"].keys())
            labels = [f"{k}: {v}" for k, v in q["options"].items()]
            prev   = answers.get(key, opts[0])
            idx    = opts.index(prev) if prev in opts else 0
            chosen = st.radio(
                f"{i + 1}. {q['question']}",
                options=labels,
                index=idx,
                key=f"radio_{key}",
            )
            answers[key] = chosen[0] if chosen else opts[0]


def render_result(secrets: dict, store) -> None:
    article   = st.session_state["reading_article"]
    questions = st.session_state["reading_questions"]
    answers   = st.session_state["reading_answers"]
    score     = st.session_state["reading_score"]

    if score is None:
        score = score_all(questions, answers)
        st.session_state["reading_score"] = score

        user    = current_user()
        user_id = user["username"] if user else "anonymous"
        doc_id  = st.session_state.get("reading_doc_id")
        if store is not None and doc_id:
            try:
                run_async(store.push_reading_attempt(
                    doc_id=doc_id, user_id=user_id,
                    answers=answers, score={"raw": score["raw"], "total": score["total"], "band": score["band"]},
                ))
            except Exception:
                pass

    st.title(f"📖 Kết quả — {article['title']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Điểm", f"{score['raw']} / {score['total']}")
    col2.metric("Band", score["band"])
    col3.metric("Tỉ lệ đúng", f"{int(score['raw'] / score['total'] * 100)}%")

    st.markdown("---")

    _render_result_section("True / False / Not Given", score["tfng"],
                           [q["statement"] for q in questions.get("tfng", [])])
    _render_result_section("Matching Headings", score["headings"],
                           [f"Paragraph {q['paragraph_idx'] + 1}" for q in questions.get("headings", [])])
    _render_result_section("Fill in the Blank", score["fill_blank"],
                           [q["sentence"] for q in questions.get("fill_blank", [])])
    _render_result_section("Multiple Choice", score["mcq"],
                           [q["question"] for q in questions.get("mcq", [])])

    st.markdown("---")
    if st.button("▶ Làm bài mới", type="primary"):
        reset_state()
        st.rerun()


def _render_result_section(title: str, results: list[dict], labels: list[str]) -> None:
    if not results:
        return
    correct = sum(1 for r in results if r["correct"])
    with st.expander(f"{title} — {correct}/{len(results)}", expanded=True):
        for label, r in zip(labels, results):
            icon = "✅" if r["correct"] else "❌"
            st.markdown(f"{icon} **{label}**")
            if not r["correct"]:
                st.caption(f"Bạn trả lời: _{r['user'] or '(trống)'}_ → Đáp án đúng: **{r['expected']}**")
