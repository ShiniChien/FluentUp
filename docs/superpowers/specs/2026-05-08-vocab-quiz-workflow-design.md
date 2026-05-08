# Vocab Quiz Workflow Design

**Date:** 2026-05-08

## Overview

GitHub Actions workflow chạy mỗi 6 tiếng (7am, 1pm, 7pm, 1am VN time), tạo Google Form quiz từ vựng cho mỗi user, gửi link lên Discord.

## Trigger & Schedule

- **Platform:** GitHub Actions, `ubuntu-latest`
- **Cron:** `0 1,7,13,19 * * *` (UTC — tương đương 7:00, 13:00, 19:00, 01:00 ICT)
- **File:** `.github/workflows/vocab-quiz.yml`

## GitHub Secrets Required

| Secret | Value |
|--------|-------|
| `MONGODB_URI` | MongoDB connection string |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Nội dung JSON của service account credentials |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL |

Service account: `shinichien@shinichien.iam.gserviceaccount.com` (project `shinichien`).

## Script Logic (`scripts/vocab_quiz.py`)

1. Kết nối MongoDB, lấy danh sách tất cả users từ collection `users`
2. Bỏ qua user `root` (hardcoded, không có trong MongoDB)
3. Fetch **global pool**: toàn bộ documents từ collection `vocabulary` của tất cả users (dùng làm distractors cho multiple choice)
4. Với mỗi user:
   - Lấy tất cả từ của user đó, random sample tối đa 20 từ làm câu hỏi
   - Nếu user có ít hơn 20 từ, lấy tất cả
   - Bỏ qua user không có từ nào
   - Với mỗi trong 20 câu, chọn loại câu hỏi theo weighted random (xem bên dưới)
   - Gọi Google Forms API tạo quiz form
5. Gửi 1 Discord message tổng hợp tất cả link

## Loại Câu Hỏi

Mỗi câu trong form được chọn ngẫu nhiên với **weights [6, 1, 3]**:

| Weight | Loại | Mô tả |
|--------|------|-------|
| 6 | **Anh → Việt** (short-answer) | Hiện `word` (tiếng Anh), điền `notes` (tiếng Việt) |
| 1 | **Việt → Anh** (short-answer) | Hiện `notes` (tiếng Việt), điền `word` (tiếng Anh) |
| 3 | **Multiple choice** | 50-50 random chiều Anh→Việt hoặc Việt→Anh, chọn 1/4 đáp án |

**Thuật toán Multiple Choice:**
- Chiều hỏi: random 50-50 (Anh→Việt hoặc Việt→Anh)
- 1 đáp án đúng từ từ đang hỏi
- 3 distractors: sample ngẫu nhiên từ **global pool** (tất cả `notes` hoặc tất cả `word` tùy chiều), loại trừ đáp án đúng
- Shuffle 4 lựa chọn trước khi đưa vào form

## Google Forms API

**APIs cần enable trong Google Cloud Console:**
- Google Forms API
- Google Drive API

**Flow tạo form:**
1. `forms().create()` — tạo form với title `"Vocabulary Quiz - {username} - {YYYY-MM-DD}"`
2. `forms().batchUpdate()` — set `isQuiz: true`, thêm 20 câu (mix short-answer + multiple choice):
   - Short-answer: answer key case-insensitive, 1 điểm/câu
   - Multiple choice: đánh dấu đúng 1 trong 4 lựa chọn, 1 điểm/câu
   - Quiz settings: show score + correct answers immediately after submit
3. `drive().permissions().create()` — set `anyone` + `reader` để form public

**Form URL:** `https://docs.google.com/forms/d/{formId}/viewform`

## Discord Message Format

```
📚 Vocabulary Quiz - {YYYY-MM-DD} {HH:MM} ICT
• username1: https://docs.google.com/forms/d/.../viewform
• username2: https://docs.google.com/forms/d/.../viewform
```

Gửi qua HTTP POST đến `DISCORD_WEBHOOK_URL` với body `{"content": "..."}`.

## File Structure

```
.github/
  workflows/
    vocab-quiz.yml
scripts/
  vocab_quiz.py
  requirements-quiz.txt    ← tách riêng, không ảnh hưởng app chính
```

## `requirements-quiz.txt`

```
pymongo
google-auth
google-api-python-client
requests
```

## Edge Cases

- User có 0 từ: bỏ qua, không tạo form
- User có < 20 từ: lấy tất cả
- Google API lỗi với 1 user: log lỗi, tiếp tục các user còn lại
- Discord webhook lỗi: workflow fail với exit code 1
