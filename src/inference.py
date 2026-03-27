import torch
from transformers import T5Tokenizer, AutoModelForSeq2SeqLM
from src.utils.preprocessor import VietnamesePreprocessor
import os

class Summarizer:
    def __init__(self, model_path="../src/model/results_vit5/vit5_model"):
        print("--- Đang nạp mô hình và cấu hình... ---")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.tokenizer = T5Tokenizer.from_pretrained(
            model_path, 
            use_fast=False, 
            legacy=True
        )
        
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval() 
        self.preprocessor = VietnamesePreprocessor()

    def summarize(self, raw_text):
        processed = self.preprocessor.run_on_text(raw_text)
        clean_text = processed['processed'] 
        
        if not clean_text:
            return "Văn bản không hợp lệ hoặc quá ngắn."

        inputs = self.tokenizer(
            clean_text, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=1024
        ).to(self.device)

        with torch.no_grad():
            output_sequences = self.model.generate(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_new_tokens=256,
                min_length=40,
                num_beams=4, 
                length_penalty=1.2,
                early_stopping=True
            )

        summary = self.tokenizer.decode(output_sequences[0], skip_special_tokens=True)
        
        final_summary = summary.replace("_", " ")
        return final_summary

if __name__ == "__main__":
    # Khởi tạo
    summarizer = Summarizer()

    # Thử nghiệm với một đoạn văn bản mẫu
    test_article = """
    Ngày 26/3, Công ty X đã ra mắt dòng sản phẩm chip xử lý mới nhất dành cho trí tuệ nhân tạo. 
    Dòng chip này được kỳ vọng sẽ tăng hiệu năng xử lý lên gấp 3 lần so với thế hệ tiền nhiệm 
    trong khi tiết kiệm năng lượng hơn 40%. Đây là bước tiến lớn của ngành công nghệ bán dẫn 
    Việt Nam trong bối cảnh cuộc đua AI đang nóng dần lên trên toàn cầu.
    """

    print("\n--- BÀI BÁO GỐC ---")
    print(test_article.strip())
    
    result = summarizer.summarize(test_article)
    
    print("\n--- BẢN TÓM TẮT CỦA AI ---")
    print(result)