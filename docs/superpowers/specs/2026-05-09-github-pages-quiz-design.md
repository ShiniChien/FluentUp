# GitHub Pages Quiz Design

**Date:** 2026-05-09

## Overview

Thay thế Google Forms bằng HTML quiz tĩnh deploy lên GitHub Pages. Workflow tạo file HTML per-user, push lên branch `gh-pages`, gửi link Discord.

## Context

Repo: `ShiniChien/FluentUp` (private)
GitHub Pages URL base: `https://shinichien.github.io/FluentUp/`
Quiz files: `https://shinichien.github.io/FluentUp/quiz/{username}_{YYYY-MM-DD}_{HH-MM}.html`

## Architecture

```
Workflow chạy (mỗi 6h từ 7am ICT):
  1. Checkout repo
  2. Install dependencies (pymongo, requests)
  3. Run scripts/vocab_quiz.py:
       a. Fetch users + vocabulary từ MongoDB
       b. Random 20 từ/user → build questions (weights [6,1,3])
       c. generate_quiz_html() → HTML string per user
       d. cleanup_old_quiz_files() → xóa file > 3 ngày trong quiz/
       e. Ghi file quiz/{username}_{date}_{time}.html
  4. Push folder quiz/ lên branch gh-pages (peaceiris/actions-gh-pages@v3)
  5. send_discord() → 1 message với tất cả link
```

## HTML Quiz (client-side)

Mỗi file `quiz/{username}_{YYYY-MM-DD}_{HH-MM}.html` là self-contained:

- **Short-answer (en_vi / vi_en):** `<input type="text">`, so sánh case-insensitive khi submit
- **Multiple choice:** 4 radio buttons, shuffle thứ tự
- **Submit button:** JS client-side tô màu xanh/đỏ từng câu, hiện `Score: N/20` ở đầu
- Đáp án nhúng trong JS bên trong HTML (repo private)
- Không có timer, không có backend

## File Lifecycle

- Filename: `quiz/shinichien_2026-05-09_07-00.html`
- Mỗi run tạo file mới (không ghi đè)
- `cleanup_old_quiz_files(quiz_dir, days=3)`: xóa file có timestamp > 3 ngày trong tên file
- GC chạy trước khi push mỗi lần

## Changes to `scripts/vocab_quiz.py`

**Xóa:**
- `create_quiz_form()`
- `_get_google_credentials()`
- `_SCOPES`
- imports: `google.oauth2`, `googleapiclient`, `json`

**Thêm:**
- `generate_quiz_html(username: str, questions: list[dict]) -> str`
- `cleanup_old_quiz_files(quiz_dir: str, days: int = 3) -> None`

**Sửa `main()`:**
- Ghi HTML files vào `quiz/` folder (working directory)
- Xóa file cũ trước khi push
- Discord message dùng GitHub Pages URL

## `.github/workflows/vocab-quiz.yml`

**Xóa env vars:** `GOOGLE_SERVICE_ACCOUNT_KEY_FILE`

**Thêm steps:**
```yaml
- name: Push quiz files to gh-pages
  uses: peaceiris/actions-gh-pages@v3
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    publish_dir: ./quiz
    destination_dir: quiz
    keep_files: true   # giữ file cũ, GC script đã xóa những file quá hạn
```

## `scripts/requirements-quiz.txt`

Xóa:
```
google-auth==2.29.0
google-api-python-client==2.128.0
```

## Discord Message Format

```
📚 Vocabulary Quiz - 2026-05-09 07:00 ICT
• shinichien: https://shinichien.github.io/FluentUp/quiz/shinichien_2026-05-09_07-00.html
• user2: https://shinichien.github.io/FluentUp/quiz/user2_2026-05-09_07-00.html
```

## Edge Cases

- User 0 từ: skip, không tạo file
- User < 20 từ: lấy tất cả
- GC chỉ xóa file match pattern `{username}_{date}_{time}.html`, không xóa file khác
- Nếu gh-pages chưa tồn tại: `peaceiris/actions-gh-pages` tự tạo
