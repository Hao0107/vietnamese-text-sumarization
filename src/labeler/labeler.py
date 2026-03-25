import os
import time
from google import genai
from pymongo import MongoClient
    
# Khởi tạo Client mới
client_ai = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = 'models/gemini-3.1-flash-lite-preview'
# MODEL_ID = 'models/gemini-2.5-flash'
# MODEL_ID = 'models/gemini-2.5-flash-lite'
# MODEL_ID = 'models/gemma-3-12b-it'

# Kết nối MongoDB
db_client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = db_client["nlp_database"]
collection = db["raw_articles"]

def summarize_text(text):
    prompt = f"""
        ### VAI TRÒ
        Bạn là một chuyên gia phân tích dữ liệu và biên tập tin tức có 20 năm kinh nghiệm. Nhiệm vụ của bạn là tạo bản tóm tắt chuẩn cho các văn bản tiếng Việt.

        ### NHIỆM VỤ
        Tóm tắt nội dung văn bản được cung cấp bên dưới theo các tiêu chí khắt khe sau:
        1. ĐỘ DÀI: Chỉ từ 2 đến 5 câu (không quá 100 từ).
        2. NỘI DUNG: Phải bao quát được sự kiện chính (Ai làm gì? Ở đâu? Khi nào? Kết quả thế nào?).
        3. THỰC THỂ: Giữ chính xác 100% tên riêng (người, tổ chức), địa danh và các con số thống kê quan trọng.
        4. PHONG CÁCH: Khách quan, không thêm nhận xét cá nhân, không mở đầu bằng "Bài báo nói về..." hay "Tóm tắt là...". Hãy đi thẳng vào nội dung.
        5. Sau khi tóm tắt xong hãy kiểm tra lại xem bản tóm tắt trên có thông tin nào mà không có trong văn bản gốc không? Nếu có thông tin không có trong văn bản gốc hãy lược bỏ. 
        Chỉ giữ lại những thông tin có trong văn bản gốc. Không thêm chú thích, không giải thích, không bình luận, chỉ trả về bản tóm tắt.
        6. Vì đây là văn bản tóm tắt nên kết quả trả về phải ngắn hơn dữ liệu đầu vào. Nếu kết quả trả về dài hơn dữ liệu đầu vào thì hãy lược bỏ bớt thông tin trong bản tóm tắt để đảm bảo kết quả trả về ngắn hơn dữ liệu đầu vào.

        ### DỮ LIỆU ĐẦU VÀO
        Nội dung văn bản:
        {text[:10000]}

        ### KẾT QUẢ TRẢ VỀ (OUTPUT)
        [Chỉ trả về nội dung tóm tắt, không kèm theo bất kỳ lời dẫn giải nào khác]
        """
    try:
        # Cấu trúc gọi mới của SDK google-genai
        response = client_ai.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            print("Hết hạn mức (Rate limit). Nghỉ 60s...")
            time.sleep(60)
        else:
            print(f"Lỗi: {e}")
        return None

def run_labeler():
    articles = list(collection.find({"is_summarized": False}))
    print(f"Đang xử lý {len(articles)} bài báo...")

    for i, doc in enumerate(articles):
        print(f"[{i+1}/{len(articles)}] \n Post ID: {doc['post_id']} \n Title: {doc['title']}")
        summary = summarize_text(doc['content'][:10000])
        if summary:
            collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"summary": summary, "is_summarized": True, "model_used": MODEL_ID}}
            )
            
            print(" - Summarized successfully. \n --content:", summary[:50], "...")
            
            time.sleep(6)

if __name__ == "__main__":
    run_labeler()