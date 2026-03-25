import re
import os
from collections import Counter
from pymongo import MongoClient

# Kết nối MongoDB
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["nlp_database"]
collection = db["raw_articles"]

def is_potential_teencode(word):
    """
    Luật để nhận diện một từ có khả năng là teencode/viết tắt:
    1. Độ dài ngắn (1-4 ký tự).
    2. Không chứa nguyên âm (đặc trưng của viết tắt như 'đc', 'ng', 'kh').
    3. Hoặc chứa các ký tự lạ không phổ biến trong tiếng Việt chuẩn.
    """
    # Loại bỏ số và ký tự đặc biệt
    if not word.isalpha():
        return False
    
    # Nếu từ chỉ toàn phụ âm (ví dụ: đc, kh, ng, n, bít)
    vowels = set("aeiouyáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữự")
    has_vowel = any(char in vowels for char in word.lower())
    
    if not has_vowel and len(word) <= 4:
        return True
    
    # Nếu từ rất ngắn và không phải là các từ phổ biến (đã lọc bằng mắt)
    if len(word) <= 2 and word.lower() not in ['là', 'về', 'có', 'và', 'thì', 'mà', 'ở']:
        return True
        
    return False

def find_oov():
    # Lấy toàn bộ nội dung đã tiền xử lý
    # Lưu ý: Chúng ta quét trên 'processed_content' vì nó đã được tách từ
    cursor = collection.find({"is_preprocessed": True}, {"processed_content": 1})
    
    word_counter = Counter()
    
    print("Đang quét dữ liệu...")
    for doc in cursor:
        text = doc.get("processed_content", "")
        # Tách các từ (underthesea nối từ ghép bằng _, ta lấy từ đơn lẻ)
        words = re.findall(r'\b\w+\b', text.lower())
        word_counter.update(words)

    # Lọc ra các ứng viên
    candidates = []
    for word, count in word_counter.items():
        if is_potential_teencode(word):
            candidates.append((word, count))

    # Sắp xếp theo tần suất xuất hiện nhiều nhất
    candidates.sort(key=lambda x: x[1], reverse=True)

    print("\n--- TOP 50 TỪ TEENCODE / VIẾT TẮT ---")
    print(f"{'Từ':<10} | {'Tần suất':<10}")
    print("-" * 25)
    
    for word, count in candidates[:50]:
        print(f"{word:<10} | {count:<10}")

if __name__ == "__main__":
    find_oov()