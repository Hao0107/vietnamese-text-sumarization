import os
import time
import asyncio
import argparse
from google import genai
from pymongo import MongoClient

parser = argparse.ArgumentParser(description="NLP News Labeler with Gemini/Gemma")
parser.add_argument(
    "--model",
    type=str,
    default=os.getenv("MODEL_ID", "models/gemini-3.1-flash-lite-preview")
)
parser.add_argument(
    "--concurrency",
    type=int,
    default=5,  # Safe starting point — increase to 10-15 if quota allows
    help="Number of parallel requests"
)
args = parser.parse_args()

MODEL_ID = args.model
MAX_CONCURRENCY = args.concurrency

# Google GenAI client (sync SDK — we'll wrap it for async)
client_ai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# MongoDB connection
db_client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = db_client["nlp_database"]
collection = db["raw_articles"]

PROMPT_TEMPLATE = """
### VAI TRÒ
Bạn là một chuyên gia phân tích dữ liệu và biên tập tin tức có 20 năm kinh nghiệm. Nhiệm vụ của bạn là tạo bản tóm tắt chuẩn cho các văn bản tiếng Việt.

### NHIỆM VỤ
Tóm tắt nội dung văn bản được cung cấp bên dưới theo các tiêu chí khắt khe sau:
1. ĐỘ DÀI: Chỉ từ 2 đến 5 câu (không quá 128 từ).
2. NỘI DUNG: Phải bao quát được sự kiện chính (Ai làm gì? Ở đâu? Khi nào? Kết quả thế nào?).
3. THỰC THỂ: Giữ chính xác 100% tên riêng (người, tổ chức), địa danh và các con số thống kê quan trọng.
4. PHONG CÁCH: Khách quan, không thêm nhận xét cá nhân, không mở đầu bằng "Bài báo nói về..." hay "Tóm tắt là...". Hãy đi thẳng vào nội dung.
5. Sau khi tóm tắt xong hãy kiểm tra lại xem bản tóm tắt trên có thông tin nào mà không có trong văn bản gốc không? Nếu có thông tin không có trong văn bản gốc hãy lược bỏ.
   Chỉ giữ lại những thông tin có trong văn bản gốc. Không thêm chú thích, không giải thích, không bình luận, chỉ trả về bản tóm tắt.
6. Vì đây là văn bản tóm tắt nên kết quả trả về phải ngắn hơn dữ liệu đầu vào. Nếu kết quả trả về dài hơn dữ liệu đầu vào thì hãy lược bỏ bớt thông tin trong bản tóm tắt để đảm bảo kết quả trả về ngắn hơn dữ liệu đầu vào.

### DỮ LIỆU ĐẦU VÀO
Nội dung văn bản:
{text}

### KẾT QUẢ TRẢ VỀ (OUTPUT)
[Chỉ trả về nội dung tóm tắt, không kèm theo bất kỳ lời dẫn giải nào khác]
"""

async def summarize_async(doc, semaphore, loop, stats):
    """Call the sync Google SDK inside a thread pool, guarded by a semaphore."""
    async with semaphore:
        text = doc["content"][:10000]
        prompt = PROMPT_TEMPLATE.format(text=text)

        for attempt in range(3):  # Retry
            try:
                # Run the blocking SDK call in a thread so it doesn't block the event loop
                response = await loop.run_in_executor(
                    None,
                    lambda: client_ai.models.generate_content(
                        model=MODEL_ID,
                        contents=prompt
                    )
                )
                summary = response.text.strip()

                # Write back to MongoDB (also blocking, run in executor)
                await loop.run_in_executor(
                    None,
                    lambda: collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "summary": summary,
                            "is_summarized": True,
                            "model_used": MODEL_ID
                        }}
                    )
                )

                stats["done"] += 1
                print(f"[{stats['done']}/{stats['total']}] {doc['post_id']} — {summary[:60]}...")
                return

            except Exception as e:
                if "429" in str(e):
                    wait = 30 * (attempt + 1)  # Back-off: 30s, 60s, 90s
                    print(f"Rate limit on {doc['post_id']}. Waiting {wait}s (attempt {attempt+1}/3)...")
                    await asyncio.sleep(wait)
                else:
                    print(f"Error on {doc['post_id']}: {e}")
                    stats["failed"] += 1
                    return

        stats["failed"] += 1
        print(f"Gave up on {doc['post_id']} after 3 attempts.")


async def run_labeler_async():
    articles = list(collection.find({"is_summarized": False}))
    total = len(articles)
    print(f"--- Model: {MODEL_ID} | Concurrency: {MAX_CONCURRENCY} ---")
    print(f"Found {total} articles to process.\n")

    if not articles:
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    loop = asyncio.get_event_loop()
    stats = {"done": 0, "failed": 0, "total": total}

    tasks = [summarize_async(doc, semaphore, loop, stats) for doc in articles]
    await asyncio.gather(*tasks)

    print(f"\nDone. Success: {stats['done']} | Failed: {stats['failed']} | Total: {total}")


if __name__ == "__main__":
    start = time.time()
    asyncio.run(run_labeler_async())
    elapsed = time.time() - start
    print(f"⏱️  Total time: {elapsed:.1f}s")